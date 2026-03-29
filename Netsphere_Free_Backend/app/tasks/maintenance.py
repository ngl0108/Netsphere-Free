"""
Maintenance Tasks: 시스템 유지보수 작업
- DB 데이터 보존 정책 (Log Retention)
"""
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
import logging
from app.db.session import SessionLocal
from app.models.device import SystemMetric, InterfaceMetric, EventLog
from app.models.settings import SystemSetting

logger = logging.getLogger(__name__)


@shared_task
def run_log_retention():
    """
    [핵심] DB 데이터 보존 정책 실행
    - SystemSetting에서 backup_retention_days 값을 가져옴
    - 해당 일수보다 오래된 SystemMetric, EventLog 삭제
    - 매일 새벽 3시에 실행되도록 celery_app에서 스케줄링
    """
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}
        # 1. 보존 기간 설정 가져오기 (기본값 30일)
        setting = db.query(SystemSetting).filter(
            SystemSetting.key == "backup_retention_days"
        ).first()
        
        retention_days = 30  # Default
        if setting and setting.value:
            try:
                retention_days = int(setting.value)
            except ValueError:
                pass
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        logger.info(
            "Running log retention",
            extra={"cutoff_date": cutoff_date.strftime("%Y-%m-%d"), "retention_days": retention_days},
        )
        
        # 2. 오래된 SystemMetric 삭제
        metrics_deleted = db.query(SystemMetric).filter(
            SystemMetric.timestamp < cutoff_date
        ).delete(synchronize_session=False)

        # 2-1. 오래된 InterfaceMetric 삭제
        if_metrics_deleted = db.query(InterfaceMetric).filter(
            InterfaceMetric.timestamp < cutoff_date
        ).delete(synchronize_session=False)
        
        # 3. 오래된 EventLog 삭제
        logs_deleted = db.query(EventLog).filter(
            EventLog.timestamp < cutoff_date
        ).delete(synchronize_session=False)
        
        db.commit()
        
        result_msg = f"✅ [Maintenance] Completed. Deleted: {metrics_deleted} system metrics, {if_metrics_deleted} interface metrics, {logs_deleted} event logs (older than {retention_days} days)"
        logger.info(
            "Log retention completed",
            extra={
                "metrics_deleted": metrics_deleted,
                "if_metrics_deleted": if_metrics_deleted,
                "logs_deleted": logs_deleted,
                "retention_days": retention_days,
            },
        )
        return result_msg
        
    except Exception as e:
        logger.exception("Log retention failed")
        db.rollback()
        return f"Error: {e}"
    finally:
        db.close()
