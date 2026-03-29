try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from app.db.session import SessionLocal
from app.services.neighbor_crawl_service import NeighborCrawlService


@shared_task(name="app.tasks.discovery_hint_prefetch.run_discovery_hint_prefetch_job")
def run_discovery_hint_prefetch_job(job_id: int, seed_device_id: int | None = None, seed_ip: str | None = None):
    db = SessionLocal()
    try:
        svc = NeighborCrawlService(db)
        return svc.prefetch_seed_context(job_id=job_id, seed_device_id=seed_device_id, seed_ip=seed_ip)
    finally:
        db.close()
