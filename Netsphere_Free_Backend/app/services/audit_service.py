from sqlalchemy.orm import Session
from app.models.audit import AuditLog
import json
from typing import Any
import logging
from app.services.audit_chain_service import AuditChainService
from app.services.pii_masking_service import PiiMaskingService

logger = logging.getLogger(__name__)

class AuditService:
    @staticmethod
    def log(db: Session, user: Any, action: str, resource_type: str, resource_name: str, details: str = None, status: str = "success", ip: str = None):
        """
        Write an audit log entry.
        """
        try:
            # Try to extract user info safely
            user_id = getattr(user, 'id', None)
            username = getattr(user, 'username', 'system') if user else 'system'
            
            # If details is a dict/list, convert to string
            if isinstance(details, (dict, list)):
                details = json.dumps(details, default=str)

            log_entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                resource_type=resource_type,
                resource_name=resource_name,
                details=details,
                status=status,
                ip_address=ip
            )
            db.add(log_entry)
            db.flush()
            if AuditChainService.enabled(db):
                AuditChainService.seal_entry(db, log_entry)
                try:
                    AuditChainService.send_syslog(
                        db,
                        json.dumps(
                            {
                                "type": "audit",
                                "id": log_entry.id,
                                "ts": str(getattr(log_entry, "timestamp", "") or ""),
                                "user": username,
                                "ip": ip,
                                "action": action,
                                "resource": resource_name,
                                "status": status,
                                "hash": log_entry.chain_hash,
                                "prev": log_entry.chain_prev_hash,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        ),
                    )
                except Exception:
                    pass
            db.commit()
        except Exception as e:
            logger.exception("Failed to write audit log")
            # db.rollback() # Don't rollback main transaction if audit fails? Or maybe create new session? 
            # Ideally audit should be safe.

    @staticmethod
    def get_logs(db: Session, skip: int = 0, limit: int = 100, filter_action: str = None):
        query = db.query(AuditLog)
        if filter_action and filter_action != 'all':
            query = query.filter(AuditLog.action == filter_action)
        return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def get_logs_serialized(db: Session, skip: int = 0, limit: int = 100, filter_action: str = None):
        logs = AuditService.get_logs(db, skip=skip, limit=limit, filter_action=filter_action)
        policy = PiiMaskingService.get_policy(db)
        out = []
        for log in logs:
            out.append(
                {
                    "id": log.id,
                    "user_id": log.user_id,
                    "username": PiiMaskingService.mask_text(log.username, policy),
                    "ip_address": PiiMaskingService.mask_text(log.ip_address, policy),
                    "action": log.action,
                    "resource_type": PiiMaskingService.mask_text(log.resource_type, policy),
                    "resource_name": PiiMaskingService.mask_text(log.resource_name, policy),
                    "details": PiiMaskingService.mask_text(log.details, policy),
                    "status": log.status,
                    "chain_prev_hash": log.chain_prev_hash,
                    "chain_hash": log.chain_hash,
                    "chain_alg": log.chain_alg,
                    "chain_version": log.chain_version,
                    "timestamp": log.timestamp,
                }
            )
        return out
