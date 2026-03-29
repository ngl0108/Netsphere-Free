try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator
from sqlalchemy.orm import Session
import logging
import time

from app.db.session import SessionLocal
from app.models.discovery import DiscoveryJob
from app.models.settings import SystemSetting
from app.services.collector_runtime_service import CollectorRuntimeService
from app.services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)


def _get_int_setting(db: Session, key: str, default: int) -> int:
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        raw = (row.value if row and row.value is not None else "")
        return int(str(raw).strip())
    except Exception:
        return default


@shared_task(name="app.tasks.discovery.run_discovery_job")
def run_discovery_job(job_id: int):
    db: Session = SessionLocal()
    try:
        job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
        if not job:
            return
        if job.status in {"running", "completed", "failed"}:
            return

        max_parallel = _get_int_setting(db, "discovery_max_parallel_jobs", 1)
        max_parallel = max(1, min(20, max_parallel))
        running = (
            db.query(DiscoveryJob)
            .filter(DiscoveryJob.status == "running", DiscoveryJob.id != job_id)
            .count()
        )
        if running >= max_parallel:
            delay = _get_int_setting(db, "discovery_queue_delay_sec", 30)
            delay = max(5, min(600, delay))
            logger.info("Discovery job delayed job_id=%s running=%s limit=%s delay=%s", job_id, running, max_parallel, delay)
            if CollectorRuntimeService.is_local_embedded_execution_enabled():
                time.sleep(delay)
            else:
                try:
                    run_discovery_job.apply_async(args=(job_id,), countdown=delay)
                    return
                except Exception:
                    time.sleep(delay)

        service = DiscoveryService(db)
        service.run_scan_worker(job_id)
    finally:
        db.close()
