try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

import logging

from app.services.syslog_service import process_syslog_message

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.syslog_ingest.ingest_syslog")
def ingest_syslog(source_ip: str, raw_log: str) -> None:
    try:
        process_syslog_message(source_ip, raw_log)
    except Exception:
        logger.exception("Syslog ingest failed")

