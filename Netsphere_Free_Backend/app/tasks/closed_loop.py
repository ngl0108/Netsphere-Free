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
import secrets

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.user import User
from app.services.closed_loop_service import ClosedLoopService

logger = logging.getLogger(__name__)


def _get_or_create_system_actor(db):
    user = db.query(User).filter(User.username == "system").first()
    if user:
        return user

    user = User(
        username="system",
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        full_name="System Automation",
        role="admin",
        is_active=True,
        must_change_password=False,
        eula_accepted=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@shared_task(name="app.tasks.closed_loop.run_closed_loop_cycle")
def run_closed_loop_cycle(dry_run: bool | None = None, site_id: int | None = None, device_id: int | None = None):
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService
        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}

        if not ClosedLoopService.engine_enabled(db):
            return {"status": "skipped", "reason": "engine_disabled"}

        actor = _get_or_create_system_actor(db)
        snapshot = ClosedLoopService.build_signal_snapshot(db, site_id=site_id, device_id=device_id)
        run_dry = bool(dry_run) if dry_run is not None else False

        out = ClosedLoopService.evaluate(
            db,
            signals=snapshot,
            actor_user=actor,
            dry_run=run_dry,
        )
        decisions = list(out.get("decisions") or [])
        summary_event = ClosedLoopService.emit_evaluation_summary(
            db,
            result=out,
            dry_run=bool(run_dry),
            source="scheduler",
            site_id=site_id,
            device_id=device_id,
            snapshot_summary=snapshot.get("summary") if isinstance(snapshot, dict) else {},
            commit=True,
        )

        return {
            "status": "ok",
            "dry_run": bool(run_dry),
            "site_id": site_id,
            "device_id": device_id,
            "snapshot_summary": snapshot.get("summary") if isinstance(snapshot, dict) else {},
            "triggered": int(out.get("triggered") or 0),
            "executed": int(out.get("executed") or 0),
            "blocked": int(out.get("blocked") or 0),
            "approvals_opened": int(summary_event.get("approvals_opened") or 0),
            "rules_total": int(out.get("rules_total") or 0),
            "auto_execute_enabled": bool(out.get("auto_execute_enabled")),
            "decisions": decisions,
        }
    except Exception as e:
        logger.exception("closed-loop cycle failed")
        db.rollback()
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()
