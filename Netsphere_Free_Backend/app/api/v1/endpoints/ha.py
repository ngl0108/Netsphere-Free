from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends
from app.api import deps
from app.models.user import User

router = APIRouter()


@router.get("/status")
def ha_status(request: Request, current_user: User = Depends(deps.require_super_admin)):
    mgr = getattr(request.app.state, "ha_manager", None)
    state = mgr.get_state() if mgr else None
    if not state:
        return {"enabled": False, "role": "disabled", "node_id": None, "leader_id": None}
    leader_url = None
    try:
        from app.db.session import SessionLocal
        from app.services.ha_service import HaService
        db = SessionLocal()
        try:
            leader_url = HaService.leader_url(db)
        finally:
            db.close()
    except Exception:
        leader_url = None
    return {
        "enabled": state.enabled,
        "role": state.role,
        "node_id": state.node_id,
        "lease_key": state.lease_key,
        "leader_id": state.leader_id,
        "leader_url": leader_url,
        "lease_expires_at": state.lease_expires_at.isoformat() if state.lease_expires_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
