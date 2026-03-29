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
from app.services.smart_alerting_service import run_alert_correlation, run_dynamic_threshold_alerts
import logging

logger = logging.getLogger(__name__)


@shared_task
def run_dynamic_thresholds():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"evaluated": 0, "created": 0, "skipped": True, "reason": "ha_standby"}
        res = run_dynamic_threshold_alerts(db)
        db.commit()
        return res
    except Exception:
        logger.exception("dynamic threshold alerting failed")
        db.rollback()
        return {"evaluated": 0, "created": 0, "error": True}
    finally:
        db.close()


@shared_task
def run_correlations():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"evaluated": 0, "created": 0, "skipped": True, "reason": "ha_standby"}
        res = run_alert_correlation(db)
        db.commit()
        return res
    except Exception:
        logger.exception("alert correlation failed")
        db.rollback()
        return {"evaluated": 0, "created": 0, "error": True}
    finally:
        db.close()
