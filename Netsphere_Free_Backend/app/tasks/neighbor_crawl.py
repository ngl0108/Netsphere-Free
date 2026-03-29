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


@shared_task(name="app.tasks.neighbor_crawl.run_neighbor_crawl_job")
def run_neighbor_crawl_job(job_id: int, seed_device_id: int | None = None, seed_ip: str | None = None, max_depth: int = 2):
    db = SessionLocal()
    try:
        svc = NeighborCrawlService(db)
        return svc.run_neighbor_crawl(job_id=job_id, seed_device_id=seed_device_id, seed_ip=seed_ip, max_depth=max_depth)
    finally:
        db.close()
