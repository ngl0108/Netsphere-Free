try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from datetime import datetime, timedelta
import secrets

from app.db.session import SessionLocal
from app.models.settings import SystemSetting
from app.services.collector_runtime_service import CollectorRuntimeService


def _idempotency_claim(device_id: int, idempotency_key: str, ttl_seconds: int = 600) -> bool:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        key = f"device_sync_idemp:{int(device_id)}:{str(idempotency_key).strip()}"
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting and setting.value:
            try:
                expiry = datetime.fromisoformat(setting.value)
                if expiry > now:
                    return False
            except Exception:
                pass
        lock_until = now + timedelta(seconds=max(60, int(ttl_seconds)))
        if not setting:
            setting = SystemSetting(key=key, value=lock_until.isoformat(), description=key, category="system")
        else:
            setting.value = lock_until.isoformat()
        db.add(setting)
        db.commit()
        return True
    finally:
        db.close()


def dispatch_device_sync(device_id: int, *, idempotency_key: str | None = None, countdown: float | None = None) -> dict:
    did = int(device_id)
    idem = str(idempotency_key or f"auto-{did}-{secrets.token_hex(8)}").strip()
    if not _idempotency_claim(did, idem):
        return {"status": "skipped", "reason": "idempotent_duplicate", "device_id": did, "idempotency_key": idem}

    if CollectorRuntimeService.is_local_embedded_execution_enabled():
        target = getattr(ssh_sync_device, "run", ssh_sync_device)
        local = CollectorRuntimeService.enqueue(
            task_name=str(getattr(ssh_sync_device, "name", "") or getattr(target, "__name__", "ssh_sync_device")),
            target=target,
            args=[did],
            countdown=countdown,
        )
        return {**local, "device_id": did, "idempotency_key": idem}

    try:
        if countdown is not None and float(countdown) > 0:
            if hasattr(ssh_sync_device, "apply_async"):
                ssh_sync_device.apply_async(args=[did], countdown=float(countdown))
            else:
                return {"status": "queued_no_worker", "device_id": did, "idempotency_key": idem}
        else:
            if hasattr(ssh_sync_device, "delay"):
                ssh_sync_device.delay(did)
            elif hasattr(ssh_sync_device, "apply_async"):
                ssh_sync_device.apply_async(args=[did], countdown=0)
            else:
                return {"status": "queued_no_worker", "device_id": did, "idempotency_key": idem}
        return {"status": "enqueued", "device_id": did, "idempotency_key": idem}
    except Exception:
        return {"status": "queue_error", "device_id": did, "idempotency_key": idem}


def schedule_ssh_sync_batch(
    device_ids,
    interval_seconds: float = 3.0,
    jitter_seconds: float = 0.5,
    idempotency_prefix: str | None = None,
):
    if CollectorRuntimeService.is_local_embedded_execution_enabled():
        return enqueue_ssh_sync_batch(
            device_ids,
            interval_seconds=interval_seconds,
            jitter_seconds=jitter_seconds,
            idempotency_prefix=idempotency_prefix,
        )

    try:
        if hasattr(enqueue_ssh_sync_batch, "delay"):
            enqueue_ssh_sync_batch.delay(device_ids, interval_seconds, jitter_seconds, idempotency_prefix)
            return {"status": "enqueued", "scheduled": len(device_ids or [])}
        if hasattr(enqueue_ssh_sync_batch, "apply_async"):
            enqueue_ssh_sync_batch.apply_async(
                args=[device_ids, interval_seconds, jitter_seconds, idempotency_prefix],
                countdown=0,
            )
            return {"status": "enqueued", "scheduled": len(device_ids or [])}
    except Exception:
        pass

    return enqueue_ssh_sync_batch(
        device_ids,
        interval_seconds=interval_seconds,
        jitter_seconds=jitter_seconds,
        idempotency_prefix=idempotency_prefix,
    )


@shared_task(name="app.tasks.device_sync.ssh_sync_device")
def ssh_sync_device(device_id: int, idempotency_key: str | None = None):
    from app.services.device_sync_service import DeviceSyncService
    return DeviceSyncService.sync_device_job(device_id, idempotency_key=idempotency_key)


@shared_task(name="app.tasks.device_sync.enqueue_ssh_sync_batch")
def enqueue_ssh_sync_batch(
    device_ids,
    interval_seconds: float = 3.0,
    jitter_seconds: float = 0.5,
    idempotency_prefix: str | None = None,
):
    """
    Schedule ssh_sync_device tasks with countdown spacing to avoid SSH bursts.
    device_ids: list[int]
    """
    try:
        ids = [int(x) for x in (device_ids or [])]
    except Exception:
        ids = []

    if not ids:
        return {"scheduled": 0}

    interval = float(interval_seconds or 0)
    jitter = float(jitter_seconds or 0)
    if interval < 0:
        interval = 0
    if jitter < 0:
        jitter = 0

    import random

    scheduled = 0
    raw_prefix = str(idempotency_prefix or "").strip()
    nonce = secrets.token_hex(4) if not raw_prefix else ""
    for i, d_id in enumerate(ids):
        countdown = (i * interval) + (random.random() * jitter if jitter else 0)
        if raw_prefix:
            idem = f"batch:{raw_prefix}:{int(d_id)}"
        else:
            idem = f"batch:{nonce}:{int(d_id)}:{int(i)}"
        dispatch = dispatch_device_sync(
            d_id,
            idempotency_key=idem,
            countdown=countdown,
        )
        if dispatch.get("status") in {"enqueued", "queued_no_worker"}:
            scheduled += 1

    return {"scheduled": scheduled, "interval_seconds": interval, "jitter_seconds": jitter}
