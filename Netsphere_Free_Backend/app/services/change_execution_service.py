from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import time
from typing import Any, Callable, Dict, List, Sequence

from app.db.session import SessionLocal
from app.models.device import EventLog
from app.models.settings import SystemSetting
from sqlalchemy.orm import Session


class ChangeExecutionService:
    CHANGE_KPI_EVENT_ID = "CHANGE_EXECUTION_KPI"

    @staticmethod
    def _normalize_device_ids(device_ids: Sequence[int]) -> List[int]:
        out: List[int] = []
        seen = set()
        for raw in list(device_ids or []):
            try:
                did = int(raw)
            except Exception:
                continue
            if did in seen:
                continue
            seen.add(did)
            out.append(did)
        return out

    @staticmethod
    def build_waves(
        device_ids: Sequence[int],
        *,
        wave_size: int = 0,
        canary_count: int = 0,
    ) -> List[List[int]]:
        ids = ChangeExecutionService._normalize_device_ids(device_ids)
        if not ids:
            return []

        try:
            ws = int(wave_size or 0)
        except Exception:
            ws = 0
        try:
            cc = int(canary_count or 0)
        except Exception:
            cc = 0
        if ws < 0:
            ws = 0
        if cc < 0:
            cc = 0

        waves: List[List[int]] = []
        rest = list(ids)
        if cc > 0:
            canary = rest[:cc]
            rest = rest[len(canary):]
            if canary:
                waves.append(canary)

        if not rest:
            return waves

        if ws <= 0:
            waves.append(rest)
            return waves

        for i in range(0, len(rest), ws):
            chunk = rest[i : i + ws]
            if chunk:
                waves.append(chunk)
        return waves

    @staticmethod
    def make_fingerprint(scope: str, payload: Dict[str, Any]) -> str:
        serial = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(serial.encode("utf-8")).hexdigest()
        return f"{str(scope or '').strip()}:{digest[:24]}"

    @staticmethod
    def claim_idempotency(
        scope: str,
        idempotency_key: str,
        ttl_seconds: int = 120,
        db: Session | None = None,
    ) -> bool:
        key_raw = str(idempotency_key or "").strip()
        if not key_raw:
            return True

        owns_session = db is None
        session = db if db is not None else SessionLocal()
        try:
            now = datetime.utcnow()
            setting_key = f"change_exec_idemp:{str(scope or '').strip()}:{key_raw}"
            row = session.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
            if row and row.value:
                try:
                    expiry = datetime.fromisoformat(str(row.value))
                    if expiry > now:
                        return False
                except Exception:
                    pass

            lock_until = now + timedelta(seconds=max(15, int(ttl_seconds or 0)))
            if not row:
                row = SystemSetting(
                    key=setting_key,
                    value=lock_until.isoformat(),
                    description=setting_key,
                    category="system",
                )
            else:
                row.value = lock_until.isoformat()
            session.add(row)
            session.commit()
            return True
        finally:
            if owns_session:
                session.close()

    @staticmethod
    def execute_wave_batches(
        waves: Sequence[Sequence[int]],
        run_wave: Callable[[List[int], int], List[Dict[str, Any]]],
        *,
        stop_on_wave_failure: bool = True,
        inter_wave_delay_seconds: float = 0.0,
        is_failure: Callable[[Dict[str, Any]], bool] | None = None,
    ) -> Dict[str, Any]:
        planned_waves = [list(w) for w in list(waves or []) if list(w)]
        results: List[Dict[str, Any]] = []
        halted = False
        halted_wave = None
        waves_executed = 0

        def _default_is_failure(row: Dict[str, Any]) -> bool:
            status = str((row or {}).get("status") or "").strip().lower()
            return status not in {"success", "dry_run"}

        judge = is_failure or _default_is_failure

        for wave_no, wave_device_ids in enumerate(planned_waves, start=1):
            waves_executed += 1
            wave_rows = run_wave(list(wave_device_ids), wave_no) or []

            normalized_rows: List[Dict[str, Any]] = []
            for r in wave_rows:
                row = dict(r or {})
                if "wave" not in row:
                    row["wave"] = wave_no
                did = row.get("device_id")
                if did is None:
                    did = row.get("id")
                if did is not None and "id" not in row:
                    row["id"] = did
                if did is not None and "device_id" not in row:
                    row["device_id"] = did
                normalized_rows.append(row)

            results.extend(normalized_rows)
            wave_failed = any(judge(r) for r in normalized_rows)
            if wave_failed and bool(stop_on_wave_failure):
                halted = True
                halted_wave = wave_no
                for tail_wave_no in range(wave_no + 1, len(planned_waves) + 1):
                    for tail_dev_id in planned_waves[tail_wave_no - 1]:
                        results.append(
                            {
                                "id": int(tail_dev_id),
                                "device_id": int(tail_dev_id),
                                "status": "skipped_wave_halt",
                                "error": f"Skipped due to failure in wave {wave_no}",
                                "wave": int(tail_wave_no),
                            }
                        )
                break

            if inter_wave_delay_seconds and float(inter_wave_delay_seconds) > 0 and wave_no < len(planned_waves):
                time.sleep(float(inter_wave_delay_seconds))

        return {
            "results": results,
            "execution": {
                "waves_total": len(planned_waves),
                "waves_executed": int(waves_executed),
                "halted": bool(halted),
                "halted_wave": int(halted_wave) if halted_wave is not None else None,
            },
        }

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _is_change_event_candidate(status: str) -> bool:
        st = str(status or "").strip().lower()
        if not st:
            return False
        if st in {"dry_run", "skipped_idempotent"}:
            return False
        if st.startswith("skipped_"):
            return False
        return True

    @staticmethod
    def _build_change_kpi_payload(
        row: Dict[str, Any],
        *,
        change_type: str,
        default_approval_id: int | None = None,
        default_execution_id: str | None = None,
    ) -> Dict[str, Any] | None:
        data = dict(row or {})
        nested = data.get("result") if isinstance(data.get("result"), dict) else {}

        status_raw = str(data.get("status") or nested.get("status") or "").strip().lower()
        if not ChangeExecutionService._is_change_event_candidate(status_raw):
            return None

        device_id = ChangeExecutionService._safe_int(
            data.get("device_id") if data.get("device_id") is not None else data.get("id")
        )
        if device_id is None:
            device_id = ChangeExecutionService._safe_int(
                nested.get("device_id") if nested.get("device_id") is not None else nested.get("id")
            )
        if device_id is None:
            return None

        post_check = data.get("post_check") if isinstance(data.get("post_check"), dict) else None
        if post_check is None:
            post_check = nested.get("post_check") if isinstance(nested.get("post_check"), dict) else None

        rollback_obj = data.get("rollback") if isinstance(data.get("rollback"), dict) else None
        if rollback_obj is None:
            rollback_obj = nested.get("rollback") if isinstance(nested.get("rollback"), dict) else None

        post_check_failed = bool(post_check) and not bool(post_check.get("ok"))
        if status_raw in {"postcheck_failed", "post_check_failed"}:
            post_check_failed = True
        rollback_attempted = bool(data.get("rollback_attempted")) or bool(nested.get("rollback_attempted"))
        rollback_success = bool(data.get("rollback_success")) or bool(nested.get("rollback_success"))
        if rollback_obj is not None:
            rollback_attempted = rollback_attempted or bool(rollback_obj.get("attempted"))
            rollback_success = rollback_success or bool(rollback_obj.get("success"))

        rollback_duration_ms = ChangeExecutionService._safe_int(
            data.get("rollback_duration_ms")
            if data.get("rollback_duration_ms") is not None
            else nested.get("rollback_duration_ms")
        )
        if rollback_duration_ms is None and rollback_obj is not None:
            rollback_duration_ms = ChangeExecutionService._safe_int(rollback_obj.get("duration_ms"))

        error_msg = str(data.get("error") or nested.get("error") or "").strip()
        failure_cause = str(data.get("failure_cause") or nested.get("failure_cause") or "").strip().lower() or None

        if not failure_cause and status_raw not in {"success", "ok"}:
            err = error_msg.lower()
            if post_check_failed and rollback_attempted and not rollback_success:
                failure_cause = "post_check_failed_rollback_failed"
            elif post_check_failed:
                failure_cause = "post_check_failed"
            elif status_raw == "precheck_failed":
                failure_cause = "precheck_failed"
            elif status_raw == "validation_failed":
                failure_cause = "validation_failed"
            elif "credential" in err or "ssh password not set" in err:
                failure_cause = "credential_missing"
            elif "connection failed" in err:
                failure_cause = "connection_failed"
            elif rollback_attempted and not rollback_success:
                failure_cause = "rollback_failed"
            elif status_raw.startswith("gate_failed_"):
                failure_cause = status_raw
            else:
                failure_cause = "execution_failed"

        approval_id = ChangeExecutionService._safe_int(
            data.get("approval_id") if data.get("approval_id") is not None else nested.get("approval_id")
        )
        if approval_id is None:
            approval_id = ChangeExecutionService._safe_int(default_approval_id)
        execution_id = str(
            data.get("execution_id")
            if data.get("execution_id") is not None
            else (nested.get("execution_id") if nested.get("execution_id") is not None else default_execution_id or "")
        ).strip() or None
        wave = ChangeExecutionService._safe_int(data.get("wave") if data.get("wave") is not None else nested.get("wave"))

        return {
            "status": "ok" if status_raw in {"success", "ok"} else "failed",
            "raw_status": status_raw,
            "change_type": str(change_type or "change"),
            "device_id": int(device_id),
            "approval_id": int(approval_id) if approval_id is not None else None,
            "execution_id": str(execution_id) if execution_id is not None else None,
            "wave": int(wave) if wave is not None else None,
            "post_check_failed": bool(post_check_failed),
            "rollback_attempted": bool(rollback_attempted),
            "rollback_success": bool(rollback_success),
            "rollback_duration_ms": int(rollback_duration_ms) if rollback_duration_ms is not None else None,
            "failure_cause": failure_cause,
            "error": error_msg or None,
            "timestamp": datetime.now().isoformat(),
        }

    @staticmethod
    def emit_change_kpi_events(
        db: Session,
        *,
        rows: Sequence[Dict[str, Any]],
        change_type: str,
        source: str,
        default_approval_id: int | None = None,
        default_execution_id: str | None = None,
        commit: bool = True,
    ) -> Dict[str, int]:
        emitted = 0
        skipped = 0
        for row in list(rows or []):
            payload = ChangeExecutionService._build_change_kpi_payload(
                dict(row or {}),
                change_type=str(change_type or "change"),
                default_approval_id=default_approval_id,
                default_execution_id=default_execution_id,
            )
            if not payload:
                skipped += 1
                continue
            db.add(
                EventLog(
                    device_id=int(payload["device_id"]),
                    severity="info" if payload.get("status") == "ok" else "warning",
                    event_id=ChangeExecutionService.CHANGE_KPI_EVENT_ID,
                    message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                    source=str(source or "ChangeExecution"),
                    timestamp=datetime.now(),
                )
            )
            emitted += 1
        if commit and emitted > 0:
            db.commit()
        return {"emitted": int(emitted), "skipped": int(skipped)}
