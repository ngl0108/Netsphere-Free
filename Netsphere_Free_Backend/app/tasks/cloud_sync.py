from __future__ import annotations

try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from datetime import datetime, timedelta, timezone
import logging

from app.db.session import SessionLocal
from app.models.cloud import CloudAccount
from app.models.settings import SystemSetting
from app.schemas.cloud import CloudPipelineRunRequest
from app.services.cloud_pipeline_service import CloudPipelineService

logger = logging.getLogger(__name__)


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _setting_value(db, key: str, default: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row and row.value is not None:
        return str(row.value)
    return str(default)


def _setting_bool(db, key: str, default: bool) -> bool:
    return _truthy(_setting_value(db, key, "true" if default else "false"), default=default)


def _setting_int(db, key: str, default: int) -> int:
    try:
        return max(30, int(float(_setting_value(db, key, str(default)))))
    except Exception:
        return int(default)


def _normalize_ts(value):
    if value is None:
        return None
    try:
        if getattr(value, "tzinfo", None) is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    except Exception:
        return None


def _parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _acquire_cloud_auto_sync_lock(db, ttl_seconds: int) -> bool:
    now = datetime.utcnow()
    lock_until = now + timedelta(seconds=max(300, int(ttl_seconds)))
    row = db.query(SystemSetting).filter(SystemSetting.key == "cloud_auto_sync_lock").first()
    if row and getattr(row, "value", None):
        current = _parse_iso(getattr(row, "value", None))
        if current and current > now:
            return False
    if row is None:
        row = SystemSetting(
            key="cloud_auto_sync_lock",
            value=lock_until.isoformat(),
            description="cloud_auto_sync_lock",
            category="system",
        )
    else:
        row.value = lock_until.isoformat()
        row.description = row.description or "cloud_auto_sync_lock"
        row.category = row.category or "system"
    db.add(row)
    db.commit()
    return True


def _clear_cloud_auto_sync_lock(db) -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == "cloud_auto_sync_lock").first()
    if row is None:
        return
    row.value = ""
    db.add(row)
    db.commit()


@shared_task
def run_cloud_auto_sync():
    db = SessionLocal()
    lock_acquired = False
    try:
        from app.services.ha_service import HaService

        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}

        enabled = _setting_bool(db, "cloud_auto_sync_enabled", True)
        if not enabled:
            return {"status": "skipped", "reason": "disabled"}

        interval_seconds = _setting_int(db, "cloud_auto_sync_interval_seconds", 30)
        include_hybrid_build = _setting_bool(db, "cloud_auto_sync_include_hybrid_build", True)
        include_hybrid_infer = _setting_bool(db, "cloud_auto_sync_include_hybrid_infer", True)
        enrich_inferred = _setting_bool(db, "cloud_auto_sync_enrich_inferred", True)
        preflight = _setting_bool(db, "cloud_auto_sync_preflight", False)

        now = datetime.utcnow()
        stale_ids: list[int] = []
        for acc in db.query(CloudAccount).filter(CloudAccount.is_active == True).order_by(CloudAccount.id.asc()).all():  # noqa: E712
            synced_at = _normalize_ts(getattr(acc, "last_synced_at", None))
            if synced_at is None or (now - synced_at).total_seconds() >= interval_seconds:
                stale_ids.append(int(acc.id))

        if not stale_ids:
            return {
                "status": "skipped",
                "reason": "no_stale_accounts",
                "interval_seconds": interval_seconds,
            }

        lock_ttl_seconds = _setting_int(db, "cloud_auto_sync_lock_ttl_seconds", 14400)
        if not _acquire_cloud_auto_sync_lock(db, lock_ttl_seconds):
            return {
                "status": "skipped",
                "reason": "lock_held",
                "interval_seconds": interval_seconds,
                "account_ids": stale_ids,
            }
        lock_acquired = True

        bucket = int(now.timestamp()) // max(30, interval_seconds)
        req = CloudPipelineRunRequest(
            account_ids=stale_ids,
            preflight=preflight,
            include_hybrid_build=include_hybrid_build,
            include_hybrid_infer=include_hybrid_infer,
            enrich_inferred=enrich_inferred,
            continue_on_error=True,
            force=False,
            idempotency_key=f"cloud-auto-sync:{bucket}",
        )
        result = CloudPipelineService.run(
            db,
            tenant_id=None,
            owner_id=0,
            req=req,
        )
        return {
            "status": str(result.status),
            "accounts": int(result.total_accounts or 0),
            "scanned_resources": int(result.scanned_resources or 0),
            "failed_accounts": int(result.failed_accounts or 0),
            "account_ids": stale_ids,
            "interval_seconds": interval_seconds,
        }
    except Exception as exc:
        logger.exception("cloud auto sync failed")
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if lock_acquired:
            try:
                _clear_cloud_auto_sync_lock(db)
            except Exception:
                logger.exception("cloud auto sync lock release failed")
        db.close()
