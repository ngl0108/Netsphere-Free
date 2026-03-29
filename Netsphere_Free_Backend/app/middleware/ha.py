from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.session import SessionLocal
from app.services.ha_service import HaService


class HaStandbyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        mgr = getattr(request.app.state, "ha_manager", None)
        state = mgr.get_state() if mgr else None
        if not state or not state.enabled or state.role != "standby":
            return await call_next(request)

        db = SessionLocal()
        try:
            readonly = HaService.standby_readonly(db)
            leader_url = HaService.leader_url(db)
        finally:
            db.close()

        if not readonly:
            return await call_next(request)

        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.url.path.endswith("/ha/status"):
                return await call_next(request)
            retry_after = 3
            body = {
                "detail": {
                    "message": "Standby node: write operations are disabled",
                    "role": state.role,
                    "leader_id": state.leader_id,
                    "leader_url": leader_url,
                    "retry_after_seconds": retry_after,
                }
            }
            return JSONResponse(status_code=503, content=body, headers={"Retry-After": str(retry_after)})

        return await call_next(request)
