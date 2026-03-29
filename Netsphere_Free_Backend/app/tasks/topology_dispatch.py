from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from app.db.session import SessionLocal
from app.models.settings import SystemSetting
from app.services.collector_runtime_service import CollectorRuntimeService
from app.tasks.topology_refresh import refresh_device_topology


def _idempotency_claim(scope: str, idempotency_key: str, ttl_seconds: int = 1200) -> bool:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        key = f"topology_dispatch_idemp:{str(scope).strip()}:{str(idempotency_key).strip()}"
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


def _enqueue_task(task: Any, *, args: list[Any], countdown: float | None = None) -> Dict[str, Any]:
    if CollectorRuntimeService.is_local_embedded_execution_enabled():
        target = getattr(task, "run", task)
        task_name = str(getattr(task, "name", "") or getattr(target, "__name__", "task"))
        return CollectorRuntimeService.enqueue(
            task_name=task_name,
            target=target,
            args=args,
            countdown=countdown,
        )

    try:
        if countdown is not None and float(countdown) > 0:
            if hasattr(task, "apply_async"):
                task.apply_async(args=args, countdown=float(countdown))
                return {"status": "enqueued"}
            return {"status": "queue_unavailable", "reason": "no_apply_async"}

        if hasattr(task, "delay"):
            task.delay(*args)
            return {"status": "enqueued"}
        if hasattr(task, "apply_async"):
            task.apply_async(args=args, countdown=0)
            return {"status": "enqueued"}
        return {"status": "queue_unavailable", "reason": "no_task_dispatch_api"}
    except Exception as e:
        return {"status": "queue_error", "reason": f"{type(e).__name__}: {e}"}


def dispatch_topology_refresh(
    device_id: int,
    *,
    discovery_job_id: int | None = None,
    max_depth: int = 2,
    idempotency_key: str | None = None,
    countdown: float | None = None,
) -> Dict[str, Any]:
    did = int(device_id)
    depth = int(max_depth or 2)
    job_part = int(discovery_job_id) if discovery_job_id is not None else ""
    idem = str(idempotency_key or f"topology:{did}:{job_part}:{depth}").strip()
    if not _idempotency_claim("refresh", idem):
        return {"status": "skipped", "reason": "idempotent_duplicate", "device_id": did, "idempotency_key": idem}

    queued = _enqueue_task(
        refresh_device_topology,
        args=[did, discovery_job_id, depth],
        countdown=countdown,
    )
    return {**queued, "device_id": did, "idempotency_key": idem}
