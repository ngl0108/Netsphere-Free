from __future__ import annotations

import hmac
import json
import random
import time
import uuid
from hashlib import sha256
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import requests
from sqlalchemy.orm import Session

from app.models.device import EventLog
from app.models.settings import SystemSetting


class WebhookService:
    _MODES = {"generic", "servicenow", "jira", "splunk", "elastic"}
    _AUTH_TYPES = {"none", "bearer", "splunk_hec", "custom"}

    @staticmethod
    def _get_setting(db: Session, key: str, default: str = "") -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = WebhookService._get_setting(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(WebhookService._get_setting(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _get_float(db: Session, key: str, default: float) -> float:
        try:
            return float(WebhookService._get_setting(db, key, str(default)).strip())
        except Exception:
            return float(default)

    @staticmethod
    def enabled(db: Session) -> bool:
        return WebhookService._get_bool(db, "webhook_enabled", False)

    @staticmethod
    def _url(db: Session) -> str:
        return WebhookService._get_setting(db, "webhook_url", "").strip()

    @staticmethod
    def _timeout(db: Session) -> int:
        t = WebhookService._get_int(db, "webhook_timeout_seconds", 5)
        if t < 1:
            t = 1
        if t > 30:
            t = 30
        return t

    @staticmethod
    def _secret(db: Session) -> str:
        return WebhookService._get_setting(db, "webhook_secret", "").strip()

    @staticmethod
    def _delivery_mode(db: Session) -> str:
        mode = WebhookService._get_setting(db, "webhook_delivery_mode", "generic").strip().lower()
        return mode if mode in WebhookService._MODES else "generic"

    @staticmethod
    def _auth_type(db: Session) -> str:
        auth_type = WebhookService._get_setting(db, "webhook_auth_type", "none").strip().lower()
        return auth_type if auth_type in WebhookService._AUTH_TYPES else "none"

    @staticmethod
    def _auth_token(db: Session) -> str:
        return WebhookService._get_setting(db, "webhook_auth_token", "").strip()

    @staticmethod
    def _auth_header_name(db: Session) -> str:
        raw = WebhookService._get_setting(db, "webhook_auth_header_name", "Authorization").strip()
        if not raw:
            return "Authorization"
        safe = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        return safe or "Authorization"

    @staticmethod
    def _retry_attempts(db: Session) -> int:
        attempts = WebhookService._get_int(db, "webhook_retry_attempts", 3)
        if attempts < 1:
            return 1
        if attempts > 8:
            return 8
        return attempts

    @staticmethod
    def _retry_backoff_seconds(db: Session) -> float:
        backoff = WebhookService._get_float(db, "webhook_retry_backoff_seconds", 1.0)
        if backoff < 0:
            return 0.0
        if backoff > 60:
            return 60.0
        return float(backoff)

    @staticmethod
    def _retry_max_backoff_seconds(db: Session) -> float:
        max_backoff = WebhookService._get_float(db, "webhook_retry_max_backoff_seconds", 8.0)
        if max_backoff < 0:
            return 0.0
        if max_backoff > 300:
            return 300.0
        return float(max_backoff)

    @staticmethod
    def _retry_jitter_seconds(db: Session) -> float:
        jitter = WebhookService._get_float(db, "webhook_retry_jitter_seconds", 0.2)
        if jitter < 0:
            return 0.0
        if jitter > 10:
            return 10.0
        return float(jitter)

    @staticmethod
    def _retry_on_4xx(db: Session) -> bool:
        return WebhookService._get_bool(db, "webhook_retry_on_4xx", False)

    @staticmethod
    def _signature(secret: str, body: bytes) -> str:
        return hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()

    @staticmethod
    def _signature_v2(secret: str, timestamp: str, body: bytes) -> str:
        msg = f"{timestamp}.".encode("utf-8") + body
        return hmac.new(secret.encode("utf-8"), msg, sha256).hexdigest()

    @staticmethod
    def _should_retry_status(status_code: int, *, retry_on_4xx: bool) -> bool:
        if status_code >= 500:
            return True
        if status_code == 429:
            return True
        if retry_on_4xx and 400 <= int(status_code) < 500:
            return True
        return False

    @staticmethod
    def _failure_cause(*, status_code: Optional[int], error: str) -> str:
        if status_code is not None:
            sc = int(status_code)
            if sc == 429:
                return "http_429"
            if 400 <= sc < 500:
                return "http_4xx"
            if 500 <= sc < 600:
                return "http_5xx"
        msg = str(error or "").strip().lower()
        if not msg:
            return "unknown"
        if "timeout" in msg:
            return "timeout"
        if "connection" in msg or "connect" in msg:
            return "connection_error"
        if "name or service not known" in msg or "nodename nor servname" in msg:
            return "dns_error"
        if "ssl" in msg or "certificate" in msg:
            return "tls_error"
        return "exception"

    @staticmethod
    def _emit_delivery_event(
        db: Session,
        *,
        delivery_id: str,
        mode: str,
        event_type: str,
        title: str,
        message_title: str,
        severity: str,
        source: str,
        data: Optional[Dict[str, Any]],
        status: str,
        attempts: int,
        status_code: Optional[int],
        failure_cause: Optional[str],
        error: str,
        url: str,
        retry_attempts: int,
    ) -> None:
        try:
            parsed = urlsplit(str(url or "").strip())
            host = str(parsed.netloc or "").strip()
            path = str(parsed.path or "").strip() or "/"
            payload = {
                "status": str(status or "").strip().lower(),
                "delivery_id": str(delivery_id),
                "mode": str(mode),
                "event_type": str(event_type),
                "attempts": int(attempts or 0),
                "retry_attempts": int(retry_attempts or 0),
                "status_code": int(status_code) if status_code is not None else None,
                "failure_cause": str(failure_cause or "").strip() or None,
                "error": str(error or "").strip()[:500],
                "target_host": host,
                "target_path": path,
                "replay": {
                    "event_type": str(event_type),
                    "title": str(title),
                    "message": str(message_title),
                    "severity": str(severity),
                    "source": str(source),
                    "data": data or {},
                },
            }
            db.add(
                EventLog(
                    device_id=None,
                    severity="info" if str(status).lower() == "ok" else "warning",
                    event_id="NORTHBOUND_WEBHOOK_DELIVERY",
                    message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                    source="Northbound",
                )
            )
            db.flush()
        except Exception:
            # Delivery should never fail because of KPI/event logging side effects.
            pass

    @staticmethod
    def _build_payload(
        *,
        mode: str,
        event_type: str,
        title: str,
        message: str,
        severity: str,
        source: str,
        data: Optional[Dict[str, Any]],
        connector_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        options = connector_options if isinstance(connector_options, dict) else {}
        base_payload: Dict[str, Any] = {
            "type": str(event_type),
            "severity": str(severity),
            "title": str(title),
            "message": str(message),
            "source": str(source),
            "data": data or {},
        }

        if mode == "servicenow":
            table = str(options.get("servicenow_table") or "").strip() or "incident"
            return {
                "table": table,
                "short_description": str(title),
                "description": str(message),
                "severity": str(severity),
                "category": str(event_type),
                "source": str(source),
                "u_netmanager": base_payload,
            }

        if mode == "jira":
            project_key = str(options.get("jira_project_key") or "").strip()
            issue_type = str(options.get("jira_issue_type") or "").strip() or "Task"
            fields: Dict[str, Any] = {
                "summary": str(title),
                "description": str(message),
                "issuetype": {"name": str(issue_type)},
                "labels": ["netmanager", f"severity-{str(severity).lower()}", f"type-{str(event_type).lower()}"],
            }
            if project_key:
                fields["project"] = {"key": project_key}
            return {
                "fields": fields,
                "netmanager": base_payload,
            }

        if mode == "splunk":
            return {
                "time": int(time.time()),
                "host": str(source),
                "source": "netmanager",
                "sourcetype": f"netmanager:{str(event_type).lower()}",
                "event": base_payload,
            }

        if mode == "elastic":
            index_name = str(options.get("elastic_index") or "").strip() or "netsphere-events"
            return {
                "_index": index_name,
                "@timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "event": {"kind": "alert", "category": str(event_type), "severity": str(severity)},
                "message": str(message),
                "title": str(title),
                "source": {"service": str(source)},
                "netmanager": {"payload": base_payload},
            }

        return base_payload

    @staticmethod
    def _build_headers(
        *,
        db: Session,
        body: bytes,
        event_type: str,
        delivery_id: str,
        timestamp: str,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "X-NetManager-Delivery-Id": str(delivery_id),
            "X-NetManager-Event-Type": str(event_type),
            "X-NetManager-Timestamp": str(timestamp),
        }

        secret = WebhookService._secret(db)
        if secret:
            # Keep legacy signature for existing receivers.
            headers["X-NetManager-Signature"] = WebhookService._signature(secret, body)
            # Add timestamp-bound signature for replay-resistant verification.
            headers["X-NetManager-Signature-V2"] = f"sha256={WebhookService._signature_v2(secret, timestamp, body)}"

        auth_type = WebhookService._auth_type(db)
        token = WebhookService._auth_token(db)
        if token:
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "splunk_hec":
                headers["Authorization"] = f"Splunk {token}"
            elif auth_type == "custom":
                headers[WebhookService._auth_header_name(db)] = token

        return headers

    @staticmethod
    def send(
        db: Session,
        *,
        event_type: str,
        title: str,
        message: str,
        severity: str = "info",
        source: str = "netmanager",
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not WebhookService.enabled(db):
            return {"success": False, "error": "webhook disabled"}

        url = WebhookService._url(db)
        if not url:
            return {"success": False, "error": "webhook url not configured"}

        mode = WebhookService._delivery_mode(db)
        connector_options = {
            "jira_project_key": WebhookService._get_setting(db, "webhook_jira_project_key", "").strip(),
            "jira_issue_type": WebhookService._get_setting(db, "webhook_jira_issue_type", "Task").strip(),
            "servicenow_table": WebhookService._get_setting(db, "webhook_servicenow_table", "incident").strip(),
            "elastic_index": WebhookService._get_setting(db, "webhook_elastic_index", "netsphere-events").strip(),
        }
        payload = WebhookService._build_payload(
            mode=mode,
            event_type=event_type,
            title=title,
            message=message,
            severity=severity,
            source=source,
            data=data,
            connector_options=connector_options,
        )

        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        retry_attempts = WebhookService._retry_attempts(db)
        retry_on_4xx = WebhookService._retry_on_4xx(db)
        backoff_base = WebhookService._retry_backoff_seconds(db)
        backoff_max = max(backoff_base, WebhookService._retry_max_backoff_seconds(db))
        jitter = WebhookService._retry_jitter_seconds(db)
        timeout = WebhookService._timeout(db)
        delivery_id = uuid.uuid4().hex
        timestamp = str(int(time.time()))
        headers = WebhookService._build_headers(
            db=db,
            body=body,
            event_type=event_type,
            delivery_id=delivery_id,
            timestamp=timestamp,
        )

        last_error = ""
        last_status_code: Optional[int] = None
        attempts_used = 0

        for attempt in range(1, retry_attempts + 1):
            attempts_used = attempt
            try:
                resp = requests.post(url, data=body, headers=headers, timeout=timeout)
                status_code = int(resp.status_code)
                last_status_code = status_code
                if status_code < 400:
                    WebhookService._emit_delivery_event(
                        db,
                        delivery_id=delivery_id,
                        mode=mode,
                        event_type=event_type,
                        title=title,
                        message_title=message,
                        severity=severity,
                        source=source,
                        data=data,
                        status="ok",
                        attempts=attempts_used,
                        status_code=status_code,
                        failure_cause=None,
                        error="",
                        url=url,
                        retry_attempts=retry_attempts,
                    )
                    return {
                        "success": True,
                        "status_code": status_code,
                        "attempts": attempts_used,
                        "delivery_id": delivery_id,
                        "mode": mode,
                    }

                snippet = str(getattr(resp, "text", "") or "")[:500]
                last_error = f"HTTP {status_code}: {snippet}"
                if attempt >= retry_attempts or not WebhookService._should_retry_status(
                    status_code,
                    retry_on_4xx=retry_on_4xx,
                ):
                    break
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt >= retry_attempts:
                    break

            delay = min(backoff_max, backoff_base * (2 ** (attempt - 1)))
            if jitter > 0:
                delay = delay + random.uniform(0.0, jitter)
            if delay > 0:
                time.sleep(delay)

        failure_cause = WebhookService._failure_cause(status_code=last_status_code, error=last_error)
        WebhookService._emit_delivery_event(
            db,
            delivery_id=delivery_id,
            mode=mode,
            event_type=event_type,
            title=title,
            message_title=message,
            severity=severity,
            source=source,
            data=data,
            status="failed",
            attempts=attempts_used,
            status_code=last_status_code,
            failure_cause=failure_cause,
            error=last_error,
            url=url,
            retry_attempts=retry_attempts,
        )
        return {
            "success": False,
            "error": last_error or "webhook delivery failed",
            "status_code": last_status_code,
            "attempts": attempts_used,
            "delivery_id": delivery_id,
            "mode": mode,
            "failure_cause": failure_cause,
        }
