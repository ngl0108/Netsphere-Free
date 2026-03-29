#!/usr/bin/env python
from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.db.session import SessionLocal as _DIRECT_SESSION_LOCAL
    from app.models.device import EventLog as _DIRECT_EVENT_LOG
    from app.models.settings import SystemSetting as _DIRECT_SYSTEM_SETTING
    from app.services.webhook_service import WebhookService as _DIRECT_WEBHOOK_SERVICE
except Exception:
    _DIRECT_SESSION_LOCAL = None
    _DIRECT_EVENT_LOG = None
    _DIRECT_SYSTEM_SETTING = None
    _DIRECT_WEBHOOK_SERVICE = None

try:
    from app.core import config as _APP_CONFIG
except Exception:
    _APP_CONFIG = None


SUPPORTED_MODES = {"jira", "servicenow", "splunk", "elastic"}
_WEBHOOK_SETTING_KEYS = [
    "webhook_enabled",
    "webhook_url",
    "webhook_secret",
    "webhook_timeout_seconds",
    "webhook_delivery_mode",
    "webhook_auth_type",
    "webhook_auth_token",
    "webhook_auth_header_name",
    "webhook_retry_attempts",
    "webhook_retry_backoff_seconds",
    "webhook_retry_max_backoff_seconds",
    "webhook_retry_jitter_seconds",
    "webhook_retry_on_4xx",
    "webhook_jira_project_key",
    "webhook_jira_issue_type",
    "webhook_servicenow_table",
    "webhook_elastic_index",
]


def _unwrap_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return dict(raw.get("data") or {})
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _p95_int(values: List[int]) -> Optional[int]:
    if not values:
        return None
    seq = sorted(int(v) for v in values)
    idx = min(len(seq) - 1, max(0, int(math.ceil(len(seq) * 0.95) - 1)))
    return int(seq[idx])


class _ReceiverState:
    def __init__(self, *, secret: str, fail_every: int, enforce_signature: bool):
        self.secret = str(secret or "")
        self.fail_every = max(0, int(fail_every or 0))
        self.enforce_signature = bool(enforce_signature)
        self.lock = threading.Lock()
        self.total_requests = 0
        self.responses_2xx = 0
        self.responses_5xx = 0
        self.signature_valid = 0
        self.signature_invalid = 0
        self.recent: List[Dict[str, Any]] = []

    def record(self, row: Dict[str, Any]) -> None:
        with self.lock:
            self.recent.append(dict(row))
            if len(self.recent) > 200:
                self.recent = self.recent[-200:]


class _ReceiverHandler(BaseHTTPRequestHandler):
    state: _ReceiverState

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_POST(self) -> None:  # noqa: N802
        state = type(self).state
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        body_len = _to_int(self.headers.get("Content-Length"), 0)
        body = self.rfile.read(max(0, body_len))
        timestamp = str(self.headers.get("X-NetManager-Timestamp") or "").strip()
        sig_v2 = str(self.headers.get("X-NetManager-Signature-V2") or "").strip()

        signature_valid = False
        if state.secret and timestamp and sig_v2:
            expected = "sha256=" + hmac.new(
                state.secret.encode("utf-8"),
                f"{timestamp}.".encode("utf-8") + body,
                sha256,
            ).hexdigest()
            signature_valid = bool(hmac.compare_digest(sig_v2, expected))

        with state.lock:
            state.total_requests += 1
            request_index = int(state.total_requests)

        status = 200
        if state.enforce_signature and not signature_valid:
            status = 401
        elif state.fail_every > 0 and request_index % state.fail_every == 0:
            status = 503

        with state.lock:
            if signature_valid:
                state.signature_valid += 1
            else:
                state.signature_invalid += 1
            if status >= 500:
                state.responses_5xx += 1
            elif 200 <= status < 300:
                state.responses_2xx += 1

        payload = {
            "ok": bool(200 <= status < 300),
            "signature_valid": bool(signature_valid),
            "request_index": int(request_index),
        }
        state.record(
            {
                "request_index": int(request_index),
                "status": int(status),
                "signature_valid": bool(signature_valid),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _start_local_receiver(
    *,
    port: int,
    secret: str,
    fail_every: int,
    enforce_signature: bool,
) -> tuple[ThreadingHTTPServer, _ReceiverState]:
    state = _ReceiverState(secret=secret, fail_every=fail_every, enforce_signature=enforce_signature)

    class _Handler(_ReceiverHandler):
        pass

    _Handler.state = state
    server = ThreadingHTTPServer(("0.0.0.0", int(port)), _Handler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    return server, state


class _ApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        insecure: bool,
        login_username: str = "",
        login_password: str = "",
    ):
        self.base_url = str(base_url).rstrip("/")
        self.session = requests.Session()
        self.session.verify = not bool(insecure)
        self._token = str(token or "").strip()
        self._login_username = str(login_username or "").strip()
        self._login_password = str(login_password or "")
        if self._token:
            self.session.headers.update({"Authorization": f"Bearer {self._token}"})

    def _set_token(self, token: str) -> None:
        self._token = str(token or "").strip()
        if self._token:
            self.session.headers.update({"Authorization": f"Bearer {self._token}"})
        else:
            if "Authorization" in self.session.headers:
                del self.session.headers["Authorization"]

    def _login(self) -> bool:
        if not self._login_username or not self._login_password:
            return False
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                data={"username": self._login_username, "password": self._login_password},
                timeout=20,
            )
        except Exception:
            return False
        if resp.status_code != 200:
            return False
        try:
            body = resp.json()
        except Exception:
            return False
        token = ""
        if isinstance(body, dict):
            if isinstance(body.get("data"), dict):
                token = str((body.get("data") or {}).get("access_token") or "").strip()
            if not token:
                token = str(body.get("access_token") or "").strip()
        if not token:
            return False
        self._set_token(token)
        return True

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        fn = getattr(self.session, str(method).lower())
        resp = fn(f"{self.base_url}{path}", timeout=20, **kwargs)
        if resp.status_code != 401:
            return resp
        # Token may have expired; attempt one re-login and retry.
        if self._login():
            resp = fn(f"{self.base_url}{path}", timeout=20, **kwargs)
        return resp

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
        return self._request("get", path, params=params or {})

    def put(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        return self._request("put", path, json=payload)

    def post(self, path: str, payload: Dict[str, Any]) -> requests.Response:
        return self._request("post", path, json=payload)


class _DirectDbResponse:
    def __init__(self, status_code: int, payload: Dict[str, Any]):
        self.status_code = int(status_code)
        self._payload = dict(payload or {})
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> Dict[str, Any]:
        return dict(self._payload)


def _ensure_direct_db_runtime() -> None:
    if _DIRECT_SESSION_LOCAL is None or _DIRECT_SYSTEM_SETTING is None or _DIRECT_EVENT_LOG is None or _DIRECT_WEBHOOK_SERVICE is None:
        raise RuntimeError("direct-db mode is unavailable: backend runtime imports failed")
    if not str(os.environ.get("FIELD_ENCRYPTION_KEY") or "").strip() and not str(os.environ.get("SECRET_KEY") or "").strip():
        derived_secret = str(getattr(_APP_CONFIG, "SECRET_KEY", "") or "").strip() if _APP_CONFIG is not None else ""
        if derived_secret:
            os.environ["SECRET_KEY"] = derived_secret


def _direct_db_set_setting(db: Any, key: str, value: Any, *, category: str = "system") -> None:
    row = db.query(_DIRECT_SYSTEM_SETTING).filter(_DIRECT_SYSTEM_SETTING.key == str(key)).first()
    if isinstance(value, bool):
        stored = "true" if value else "false"
    elif value is None:
        stored = ""
    elif isinstance(value, (dict, list)):
        stored = json.dumps(value, ensure_ascii=False)
    else:
        stored = str(value)
    if row is None:
        row = _DIRECT_SYSTEM_SETTING(
            key=str(key),
            value=stored,
            description=str(key),
            category=str(category),
        )
    else:
        row.value = stored
        row.category = str(category)
    db.add(row)


def _snapshot_direct_webhook_settings() -> Dict[str, Any]:
    _ensure_direct_db_runtime()
    db = _DIRECT_SESSION_LOCAL()
    try:
        rows = (
            db.query(_DIRECT_SYSTEM_SETTING)
            .filter(_DIRECT_SYSTEM_SETTING.key.in_(list(_WEBHOOK_SETTING_KEYS)))
            .all()
        )
        existing = {str(row.key): str(row.value or "") for row in rows}
        missing = [key for key in _WEBHOOK_SETTING_KEYS if key not in existing]
        return {
            "existing": existing,
            "missing": missing,
        }
    finally:
        db.close()


def _restore_direct_webhook_settings(snapshot: Dict[str, Any]) -> None:
    _ensure_direct_db_runtime()
    existing = snapshot.get("existing") if isinstance(snapshot.get("existing"), dict) else {}
    missing = [str(key) for key in list(snapshot.get("missing") or []) if str(key).strip()]
    db = _DIRECT_SESSION_LOCAL()
    try:
        rows = (
            db.query(_DIRECT_SYSTEM_SETTING)
            .filter(_DIRECT_SYSTEM_SETTING.key.in_(list(_WEBHOOK_SETTING_KEYS)))
            .all()
        )
        by_key = {str(row.key): row for row in rows}
        for key, value in existing.items():
            _direct_db_set_setting(db, str(key), str(value), category=(by_key.get(str(key)).category if by_key.get(str(key)) is not None else "system"))
        for key in missing:
            row = by_key.get(str(key))
            if row is not None:
                db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _build_northbound_kpi_snapshot_direct() -> Dict[str, Any]:
    _ensure_direct_db_runtime()
    db = _DIRECT_SESSION_LOCAL()
    try:
        now_dt = datetime.now()
        since_nb = now_dt.timestamp() - (30 * 24 * 3600)
        since_24h = now_dt.timestamp() - (24 * 3600)
        rows = (
            db.query(_DIRECT_EVENT_LOG)
            .filter(_DIRECT_EVENT_LOG.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
            .order_by(_DIRECT_EVENT_LOG.timestamp.desc())
            .limit(5000)
            .all()
        )
        deliveries = 0
        success = 0
        failed = 0
        failed_24h = 0
        attempts_values: List[int] = []
        mode_counts: Dict[str, int] = {}
        failure_counts: Dict[str, int] = {}
        for row in rows:
            ts = getattr(row, "timestamp", None)
            if ts is None:
                continue
            try:
                if float(ts.timestamp()) < float(since_nb):
                    continue
            except Exception:
                continue
            try:
                payload = json.loads(str(getattr(row, "message", "") or ""))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            deliveries += 1
            status_text = str(payload.get("status") or "").strip().lower()
            is_success = status_text == "ok"
            if is_success:
                success += 1
            else:
                failed += 1
                try:
                    if float(ts.timestamp()) >= float(since_24h):
                        failed_24h += 1
                except Exception:
                    pass
                cause = str(payload.get("failure_cause") or "unknown").strip().lower() or "unknown"
                failure_counts[cause] = int(failure_counts.get(cause, 0)) + 1
            try:
                attempts_values.append(max(1, int(payload.get("attempts") or 1)))
            except Exception:
                attempts_values.append(1)
            mode = str(payload.get("mode") or "generic").strip().lower() or "generic"
            mode_counts[mode] = int(mode_counts.get(mode) or 0) + 1

        success_rate = 100.0 if deliveries == 0 else round((success / deliveries) * 100.0, 2)
        avg_attempts = round((sum(attempts_values) / len(attempts_values)), 2) if attempts_values else 0.0
        p95_attempts = 0
        if attempts_values:
            p95_attempts = int(_p95_int(attempts_values) or 0)

        status = "idle"
        if deliveries > 0:
            if success_rate < 80.0 or failed_24h > 20:
                status = "critical"
            elif success_rate < 95.0 or p95_attempts > 3 or failed_24h > 5:
                status = "warning"
            else:
                status = "healthy"

        return {
            "window_days": 30,
            "status": status,
            "success_rate_pct": float(success_rate),
            "avg_attempts": float(avg_attempts),
            "p95_attempts": int(p95_attempts),
            "failure_causes": sorted(
                [{"cause": key, "count": int(value)} for key, value in failure_counts.items()],
                key=lambda row: row["count"],
                reverse=True,
            )[:10],
            "modes": sorted(
                [{"mode": key, "count": int(value)} for key, value in mode_counts.items()],
                key=lambda row: row["count"],
                reverse=True,
            )[:10],
            "totals": {
                "deliveries": int(deliveries),
                "success": int(success),
                "failed": int(failed),
                "failed_24h": int(failed_24h),
            },
        }
    finally:
        db.close()


class _DirectDbClient:
    def __init__(self):
        _ensure_direct_db_runtime()

    def put(self, path: str, payload: Dict[str, Any]) -> _DirectDbResponse:
        if path != "/api/v1/settings/general":
            return _DirectDbResponse(404, {"detail": "unsupported direct-db path"})
        settings = payload.get("settings") if isinstance(payload, dict) else {}
        if not isinstance(settings, dict):
            return _DirectDbResponse(400, {"detail": "settings must be an object"})
        db = _DIRECT_SESSION_LOCAL()
        try:
            for key, value in settings.items():
                _direct_db_set_setting(db, str(key), value, category="notifications")
            db.commit()
            return _DirectDbResponse(200, {"message": "Settings updated successfully"})
        except Exception as exc:
            db.rollback()
            return _DirectDbResponse(500, {"detail": f"{type(exc).__name__}: {exc}"})
        finally:
            db.close()

    def post(self, path: str, payload: Dict[str, Any]) -> _DirectDbResponse:
        if path != "/api/v1/settings/test-webhook-connector":
            return _DirectDbResponse(404, {"detail": "unsupported direct-db path"})
        db = _DIRECT_SESSION_LOCAL()
        try:
            result = _DIRECT_WEBHOOK_SERVICE.send(
                db,
                event_type=str(payload.get("event_type") or "soak_test"),
                title=str(payload.get("title") or "Northbound Probe"),
                message=str(payload.get("message") or "direct-db probe"),
                severity="info",
                source="netmanager",
                data={"kind": "settings_test", "mode": "direct_db"},
            )
            if not result.get("success"):
                db.rollback()
                return _DirectDbResponse(400, {"detail": result.get("error") or "webhook failed"})
            db.commit()
            return _DirectDbResponse(
                200,
                {
                    "message": "Webhook sent successfully",
                    "result": {
                        "mode": result.get("mode"),
                        "status_code": result.get("status_code"),
                        "attempts": result.get("attempts"),
                        "delivery_id": result.get("delivery_id"),
                    },
                },
            )
        except Exception as exc:
            db.rollback()
            return _DirectDbResponse(500, {"detail": f"{type(exc).__name__}: {exc}"})
        finally:
            db.close()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> _DirectDbResponse:
        if path == "/api/v1/settings/general":
            _ensure_direct_db_runtime()
            db = _DIRECT_SESSION_LOCAL()
            try:
                rows = (
                    db.query(_DIRECT_SYSTEM_SETTING)
                    .filter(_DIRECT_SYSTEM_SETTING.key.in_(list(_WEBHOOK_SETTING_KEYS)))
                    .all()
                )
                return _DirectDbResponse(
                    200,
                    {str(row.key): str(row.value or "") for row in rows},
                )
            finally:
                db.close()
        if path != "/api/v1/sdn/dashboard/stats":
            return _DirectDbResponse(404, {"detail": "unsupported direct-db path"})
        return _DirectDbResponse(200, {"northbound_kpi": _build_northbound_kpi_snapshot_direct()})


def _build_markdown(report: Dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    thresholds = report.get("thresholds") if isinstance(report.get("thresholds"), dict) else {}
    receiver = report.get("local_receiver") if isinstance(report.get("local_receiver"), dict) else {}
    northbound = report.get("northbound_kpi") if isinstance(report.get("northbound_kpi"), dict) else {}
    mode_rows = report.get("mode_stats") if isinstance(report.get("mode_stats"), list) else []
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []

    lines: List[str] = []
    lines.append("# Northbound 72h Soak Verification")
    lines.append("")
    lines.append(f"- Generated (UTC): `{report.get('generated_at_utc')}`")
    lines.append(f"- Run ID: `{report.get('run_id')}`")
    lines.append(f"- Duration Seconds: `{summary.get('duration_seconds')}`")
    lines.append(f"- Overall Status: `{report.get('status')}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total Attempts: `{summary.get('total_attempts')}`")
    lines.append(f"- Success Count: `{summary.get('success_count')}`")
    lines.append(f"- Failure Count: `{summary.get('failure_count')}`")
    lines.append(f"- Success Rate: `{summary.get('success_rate_pct')}`%")
    lines.append(f"- Attempts P95: `{summary.get('attempts_p95')}`")
    lines.append("")

    lines.append("## Thresholds")
    lines.append("")
    lines.append(f"- min_success_rate_pct: `{thresholds.get('min_success_rate_pct')}`")
    lines.append(f"- max_attempts_p95: `{thresholds.get('max_attempts_p95')}`")
    lines.append(f"- max_failed_24h: `{thresholds.get('max_failed_24h')}`")
    lines.append(f"- min_signature_valid_rate_pct: `{thresholds.get('min_signature_valid_rate_pct')}`")
    lines.append("")

    if mode_rows:
        lines.append("## Per-Mode")
        lines.append("")
        lines.append("| Mode | Attempts | Success | Fail | Success Rate | Attempts P95 |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for row in mode_rows:
            lines.append(
                f"| `{row.get('mode')}` | `{row.get('attempts')}` | `{row.get('success')}` | `{row.get('fail')}` | `{row.get('success_rate_pct')}` | `{row.get('attempts_p95')}` |"
            )
        lines.append("")

    if northbound:
        lines.append("## Dashboard Northbound KPI")
        lines.append("")
        totals = northbound.get("totals") if isinstance(northbound.get("totals"), dict) else {}
        lines.append(f"- status: `{northbound.get('status')}`")
        lines.append(f"- success_rate_pct: `{northbound.get('success_rate_pct')}`")
        lines.append(f"- p95_attempts: `{northbound.get('p95_attempts')}`")
        lines.append(f"- failed_24h: `{totals.get('failed_24h')}`")
        lines.append("")

    if receiver:
        lines.append("## Local Receiver (Signature + Retry Probe)")
        lines.append("")
        lines.append(f"- enabled: `{receiver.get('enabled')}`")
        lines.append(f"- total_requests: `{receiver.get('total_requests')}`")
        lines.append(f"- signature_valid_rate_pct: `{receiver.get('signature_valid_rate_pct')}`")
        lines.append(f"- responses_5xx: `{receiver.get('responses_5xx')}`")
        lines.append("")

    if checks:
        lines.append("## Gate Checks")
        lines.append("")
        lines.append("| Check | Status | Value | Threshold |")
        lines.append("|---|---|---:|---:|")
        for c in checks:
            lines.append(
                f"| `{c.get('id')}` | `{c.get('status')}` | `{c.get('value')}` | `{c.get('threshold')}` |"
            )
        lines.append("")

    return "\n".join(lines)


def _write_progress_checkpoint(
    *,
    run_id: str,
    latest_json_path: str,
    latest_md_path: str,
    records: List[Dict[str, Any]],
    start_epoch: float,
    expected_end_epoch: float,
) -> None:
    if not latest_json_path and not latest_md_path:
        return

    total = len(records)
    success = len([r for r in records if bool(r.get("ok"))])
    failed = int(total - success)
    success_rate = round((success / total) * 100.0, 2) if total > 0 else 0.0
    now_utc = datetime.now(timezone.utc)
    last_row = records[-1] if records else {}

    payload = {
        "run_id": str(run_id),
        "status": "running",
        "generated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at_utc": datetime.fromtimestamp(start_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "expected_finish_utc": datetime.fromtimestamp(expected_end_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_attempts": int(total),
            "success_count": int(success),
            "failure_count": int(failed),
            "success_rate_pct": float(success_rate),
            "elapsed_seconds": int(max(0.0, time.time() - start_epoch)),
            "remaining_seconds": int(max(0.0, expected_end_epoch - time.time())),
        },
        "last_record": dict(last_row),
    }

    if latest_json_path:
        p = Path(str(latest_json_path))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if latest_md_path:
        p = Path(str(latest_md_path))
        p.parent.mkdir(parents=True, exist_ok=True)
        md_lines = [
            "# Northbound Soak Progress",
            "",
            f"- Run ID: `{payload['run_id']}`",
            f"- Status: `{payload['status']}`",
            f"- Generated (UTC): `{payload['generated_at_utc']}`",
            f"- Started (UTC): `{payload['started_at_utc']}`",
            f"- Expected Finish (UTC): `{payload['expected_finish_utc']}`",
            "",
            "## Summary",
            "",
            f"- Total Attempts: `{payload['summary']['total_attempts']}`",
            f"- Success Count: `{payload['summary']['success_count']}`",
            f"- Failure Count: `{payload['summary']['failure_count']}`",
            f"- Success Rate: `{payload['summary']['success_rate_pct']}`%",
            f"- Elapsed Seconds: `{payload['summary']['elapsed_seconds']}`",
            f"- Remaining Seconds: `{payload['summary']['remaining_seconds']}`",
            "",
            "## Last Record",
            "",
            f"- mode: `{payload['last_record'].get('mode')}`",
            f"- ok: `{payload['last_record'].get('ok')}`",
            f"- attempts: `{payload['last_record'].get('attempts')}`",
            f"- delivery_status_code: `{payload['last_record'].get('delivery_status_code')}`",
            f"- latency_ms: `{payload['last_record'].get('latency_ms')}`",
        ]
        p.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def _append_progress_log(path: str, message: str) -> None:
    target = str(path or "").strip()
    if not target:
        return
    try:
        p = Path(target)
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}Z] {message}\n")
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run long-run northbound connector soak verification (ITSM/SIEM) with retry and signature evidence.",
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default="")
    parser.add_argument("--login-username", default="", help="Optional login username for auto token refresh on 401.")
    parser.add_argument("--login-password", default="", help="Optional login password for auto token refresh on 401.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification.")
    parser.add_argument("--direct-db", action="store_true", help="Run self-contained probe against local DB/services without API auth.")
    parser.add_argument("--duration-hours", type=float, default=72.0)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--modes", default="jira,servicenow,splunk,elastic")

    parser.add_argument("--webhook-url", default="")
    parser.add_argument("--jira-url", default="")
    parser.add_argument("--servicenow-url", default="")
    parser.add_argument("--splunk-url", default="")
    parser.add_argument("--elastic-url", default="")

    parser.add_argument("--use-local-receiver", action="store_true")
    parser.add_argument("--local-receiver-host", default="host.docker.internal")
    parser.add_argument("--local-receiver-port", type=int, default=18080)
    parser.add_argument("--local-receiver-fail-every", type=int, default=10)
    parser.add_argument("--local-receiver-enforce-signature", action="store_true")

    parser.add_argument("--webhook-secret", default="soak-secret")
    parser.add_argument("--webhook-timeout-seconds", type=int, default=5)
    parser.add_argument("--webhook-retry-attempts", type=int, default=3)
    parser.add_argument("--webhook-retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--webhook-retry-max-backoff-seconds", type=float, default=8.0)
    parser.add_argument("--webhook-retry-jitter-seconds", type=float, default=0.2)
    parser.add_argument("--webhook-retry-on-4xx", action="store_true")

    parser.add_argument("--jira-project-key", default="NET")
    parser.add_argument("--jira-issue-type", default="Incident")
    parser.add_argument("--servicenow-table", default="incident")
    parser.add_argument("--elastic-index", default="netsphere-events")

    parser.add_argument("--min-success-rate-pct", type=float, default=95.0)
    parser.add_argument("--max-attempts-p95", type=int, default=3)
    parser.add_argument("--max-failed-24h", type=int, default=5)
    parser.add_argument("--min-signature-valid-rate-pct", type=float, default=100.0)

    parser.add_argument("--output-dir", default="docs/reports")
    parser.add_argument("--filename-prefix", default="northbound-soak")
    parser.add_argument("--latest-json-path", default="")
    parser.add_argument("--latest-md-path", default="")
    parser.add_argument("--checkpoint-interval-seconds", type=int, default=60)
    parser.add_argument("--progress-log-path", default="")
    parser.add_argument("--fail-on-threshold", action="store_true")

    args = parser.parse_args()

    if args.duration_hours <= 0:
        raise SystemExit("duration-hours must be > 0")
    if args.interval_seconds <= 0:
        raise SystemExit("interval-seconds must be > 0")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    token = str(args.token or "").strip()
    login_username = str(args.login_username or "").strip()
    login_password = str(args.login_password or "")
    if not bool(args.direct_db) and not token and not (login_username and login_password):
        raise SystemExit("Either --token or (--login-username + --login-password) is required.")

    local_server = None
    local_state = None
    direct_db_snapshot = None
    try:
        if args.use_local_receiver:
            local_server, local_state = _start_local_receiver(
                port=int(args.local_receiver_port),
                secret=str(args.webhook_secret or ""),
                fail_every=int(args.local_receiver_fail_every or 0),
                enforce_signature=bool(args.local_receiver_enforce_signature),
            )

        local_url = ""
        if args.use_local_receiver:
            local_url = f"http://{args.local_receiver_host}:{int(args.local_receiver_port)}/webhook"

        mode_url = {
            "jira": str(args.jira_url or args.webhook_url or local_url).strip(),
            "servicenow": str(args.servicenow_url or args.webhook_url or local_url).strip(),
            "splunk": str(args.splunk_url or args.webhook_url or local_url).strip(),
            "elastic": str(args.elastic_url or args.webhook_url or local_url).strip(),
        }

        requested_modes = [m.strip().lower() for m in str(args.modes or "").split(",") if m.strip()]
        modes = [m for m in requested_modes if m in SUPPORTED_MODES and mode_url.get(m)]
        if not modes:
            raise SystemExit("No active modes. Provide valid --modes and mode URLs.")

        if bool(args.direct_db):
            direct_db_snapshot = _snapshot_direct_webhook_settings()
            client = _DirectDbClient()
        else:
            client = _ApiClient(
                base_url=args.base_url,
                token=token,
                insecure=bool(args.insecure),
                login_username=login_username,
                login_password=login_password,
            )
            if not token:
                if not client._login():
                    raise RuntimeError("login failed: unable to acquire token using login credentials")
        start_at = time.time()
        end_at = start_at + (float(args.duration_hours) * 3600.0)
        current_mode = ""
        records: List[Dict[str, Any]] = []
        per_mode_attempt_values: Dict[str, List[int]] = {m: [] for m in modes}
        checkpoint_interval = max(5, int(args.checkpoint_interval_seconds or 60))
        next_checkpoint_at = 0.0
        _append_progress_log(
            str(args.progress_log_path or ""),
            f"START run_id={run_id} modes={','.join(modes)} interval_seconds={args.interval_seconds} duration_hours={args.duration_hours}",
        )

        idx = 0
        while time.time() < end_at:
            mode = modes[idx % len(modes)]
            idx += 1
            if mode != current_mode:
                settings_payload = {
                    "webhook_enabled": True,
                    "webhook_url": mode_url[mode],
                    "webhook_secret": str(args.webhook_secret or ""),
                    "webhook_timeout_seconds": int(args.webhook_timeout_seconds),
                    "webhook_delivery_mode": mode,
                    "webhook_auth_type": "none",
                    "webhook_retry_attempts": int(args.webhook_retry_attempts),
                    "webhook_retry_backoff_seconds": float(args.webhook_retry_backoff_seconds),
                    "webhook_retry_max_backoff_seconds": float(args.webhook_retry_max_backoff_seconds),
                    "webhook_retry_jitter_seconds": float(args.webhook_retry_jitter_seconds),
                    "webhook_retry_on_4xx": bool(args.webhook_retry_on_4xx),
                    "webhook_jira_project_key": str(args.jira_project_key or ""),
                    "webhook_jira_issue_type": str(args.jira_issue_type or "Task"),
                    "webhook_servicenow_table": str(args.servicenow_table or "incident"),
                    "webhook_elastic_index": str(args.elastic_index or "netsphere-events"),
                }
                put_res = client.put("/api/v1/settings/general", {"settings": settings_payload})
                if put_res.status_code >= 400:
                    raise RuntimeError(f"settings update failed [{put_res.status_code}]: {put_res.text[:300]}")
                current_mode = mode

            started = time.time()
            call_res = client.post(
                "/api/v1/settings/test-webhook-connector",
                {
                    "event_type": "soak_test",
                    "title": f"Soak Test [{mode}]",
                    "message": f"run_id={run_id} idx={idx}",
                },
            )
            latency_ms = round((time.time() - started) * 1000.0, 2)
            row: Dict[str, Any] = {
                "index": int(idx),
                "mode": mode,
                "http_status": int(call_res.status_code),
                "latency_ms": latency_ms,
                "ok": bool(call_res.status_code == 200),
                "attempts": None,
                "delivery_status_code": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            try:
                body = _unwrap_payload(call_res.json())
            except Exception:
                body = {}
            result = body.get("result") if isinstance(body, dict) and isinstance(body.get("result"), dict) else {}
            row["attempts"] = _to_int(result.get("attempts"), 0) if result else 0
            row["delivery_status_code"] = _to_int(result.get("status_code"), 0) if result else 0
            records.append(row)
            if row["attempts"] and row["attempts"] > 0:
                per_mode_attempt_values[mode].append(int(row["attempts"]))

            total = len(records)
            ok_count = len([x for x in records if bool(x.get("ok"))])
            fail_count = int(total - ok_count)
            success_rate = round((ok_count / total) * 100.0, 2) if total > 0 else 0.0
            print(
                f"[PROGRESS] run_id={run_id} idx={idx} mode={mode} ok={row['ok']} attempts={row['attempts']} "
                f"status_code={row['delivery_status_code']} success_rate={success_rate}% ok={ok_count} fail={fail_count}",
                flush=True,
            )
            _append_progress_log(
                str(args.progress_log_path or ""),
                f"PROGRESS run_id={run_id} idx={idx} mode={mode} ok={row['ok']} attempts={row['attempts']} status_code={row['delivery_status_code']} success_rate={success_rate}% ok={ok_count} fail={fail_count}",
            )

            now_ts = time.time()
            if now_ts >= next_checkpoint_at:
                _write_progress_checkpoint(
                    run_id=run_id,
                    latest_json_path=str(args.latest_json_path or ""),
                    latest_md_path=str(args.latest_md_path or ""),
                    records=records,
                    start_epoch=start_at,
                    expected_end_epoch=end_at,
                )
                next_checkpoint_at = now_ts + float(checkpoint_interval)

            if time.time() >= end_at:
                break
            time.sleep(float(args.interval_seconds))

        stats_res = client.get("/api/v1/sdn/dashboard/stats")
        if stats_res.status_code >= 400:
            raise RuntimeError(f"dashboard stats failed [{stats_res.status_code}]: {stats_res.text[:300]}")
        stats_payload = _unwrap_payload(stats_res.json())
        northbound_kpi = (
            stats_payload.get("northbound_kpi")
            if isinstance(stats_payload, dict) and isinstance(stats_payload.get("northbound_kpi"), dict)
            else {}
        )
        northbound_totals = northbound_kpi.get("totals") if isinstance(northbound_kpi.get("totals"), dict) else {}

        total_attempts = len(records)
        success_rows = [r for r in records if bool(r.get("ok"))]
        fail_rows = [r for r in records if not bool(r.get("ok"))]
        success_count = len(success_rows)
        failure_count = len(fail_rows)
        success_rate = round((success_count / total_attempts) * 100.0, 2) if total_attempts > 0 else 0.0
        attempts_values = [int(r.get("attempts") or 0) for r in records if int(r.get("attempts") or 0) > 0]
        attempts_p95 = _p95_int(attempts_values)

        mode_stats: List[Dict[str, Any]] = []
        for mode in modes:
            rows = [r for r in records if r.get("mode") == mode]
            mode_total = len(rows)
            mode_success = len([r for r in rows if bool(r.get("ok"))])
            mode_fail = mode_total - mode_success
            mode_rate = round((mode_success / mode_total) * 100.0, 2) if mode_total > 0 else 0.0
            mode_p95 = _p95_int(per_mode_attempt_values.get(mode) or [])
            mode_stats.append(
                {
                    "mode": mode,
                    "attempts": int(mode_total),
                    "success": int(mode_success),
                    "fail": int(mode_fail),
                    "success_rate_pct": float(mode_rate),
                    "attempts_p95": int(mode_p95) if mode_p95 is not None else None,
                }
            )

        local_receiver_summary: Dict[str, Any] = {"enabled": False}
        if local_state is not None:
            with local_state.lock:
                total_req = int(local_state.total_requests)
                valid = int(local_state.signature_valid)
                invalid = int(local_state.signature_invalid)
                r2xx = int(local_state.responses_2xx)
                r5xx = int(local_state.responses_5xx)
            valid_rate = round((valid / total_req) * 100.0, 2) if total_req > 0 else 0.0
            local_receiver_summary = {
                "enabled": True,
                "total_requests": total_req,
                "signature_valid": valid,
                "signature_invalid": invalid,
                "signature_valid_rate_pct": valid_rate,
                "responses_2xx": r2xx,
                "responses_5xx": r5xx,
                "fail_every": int(args.local_receiver_fail_every),
                "enforce_signature": bool(args.local_receiver_enforce_signature),
            }

        checks: List[Dict[str, Any]] = []
        def _append_check(check_id: str, value: float, threshold: float, op: str) -> None:
            if op == ">=":
                passed = bool(value >= threshold)
            else:
                passed = bool(value <= threshold)
            checks.append(
                {
                    "id": check_id,
                    "value": value,
                    "threshold": threshold,
                    "operator": op,
                    "status": "pass" if passed else "fail",
                }
            )

        _append_check("northbound.success_rate_pct", float(success_rate), float(args.min_success_rate_pct), ">=")
        _append_check("northbound.attempts_p95", float(attempts_p95 or 0), float(args.max_attempts_p95), "<=")
        _append_check(
            "northbound.failed_24h",
            float(_to_int(northbound_totals.get("failed_24h"), 0)),
            float(args.max_failed_24h),
            "<=",
        )
        if local_receiver_summary.get("enabled"):
            _append_check(
                "receiver.signature_valid_rate_pct",
                float(local_receiver_summary.get("signature_valid_rate_pct") or 0.0),
                float(args.min_signature_valid_rate_pct),
                ">=",
            )

        failed_checks = [c for c in checks if c.get("status") != "pass"]
        status = "pass" if not failed_checks else "fail"

        now_utc = datetime.now(timezone.utc)
        report: Dict[str, Any] = {
            "run_id": run_id,
            "generated_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "summary": {
                "duration_seconds": int(round(float(args.duration_hours) * 3600.0)),
                "interval_seconds": float(args.interval_seconds),
                "total_attempts": int(total_attempts),
                "success_count": int(success_count),
                "failure_count": int(failure_count),
                "success_rate_pct": float(success_rate),
                "attempts_p95": int(attempts_p95) if attempts_p95 is not None else None,
            },
            "thresholds": {
                "min_success_rate_pct": float(args.min_success_rate_pct),
                "max_attempts_p95": int(args.max_attempts_p95),
                "max_failed_24h": int(args.max_failed_24h),
                "min_signature_valid_rate_pct": float(args.min_signature_valid_rate_pct),
            },
            "scope": {
                "base_url": str(args.base_url),
                "execution_mode": "direct_db" if bool(args.direct_db) else "api",
                "modes": modes,
                "mode_urls": {k: ("set" if v else "") for k, v in mode_url.items()},
            },
            "mode_stats": mode_stats,
            "northbound_kpi": northbound_kpi,
            "local_receiver": local_receiver_summary,
            "checks": checks,
            "samples": records[-200:],
        }

        out_dir = Path(str(args.output_dir or "docs/reports"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_utc.strftime("%Y%m%d-%H%M%S")
        json_path = out_dir / f"{args.filename_prefix}-{stamp}.json"
        md_path = out_dir / f"{args.filename_prefix}-{stamp}.md"

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_build_markdown(report), encoding="utf-8")

        if str(args.latest_json_path or "").strip():
            p = Path(str(args.latest_json_path).strip())
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
        if str(args.latest_md_path or "").strip():
            p = Path(str(args.latest_md_path).strip())
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

        print(f"[OK] Soak report JSON: {json_path}")
        print(f"[OK] Soak report Markdown: {md_path}")
        print(f"[INFO] status={status} success_rate={success_rate}% attempts_p95={attempts_p95}")
        _append_progress_log(
            str(args.progress_log_path or ""),
            f"DONE run_id={run_id} status={status} success_rate={success_rate}% attempts_p95={attempts_p95}",
        )

        if args.fail_on_threshold and status != "pass":
            return 2
        return 0
    finally:
        if bool(args.direct_db) and direct_db_snapshot is not None:
            try:
                _restore_direct_webhook_settings(direct_db_snapshot)
            except Exception as exc:
                print(f"[WARN] direct-db webhook settings restore failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if local_server is not None:
            try:
                local_server.shutdown()
            except Exception:
                pass
            try:
                local_server.server_close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
