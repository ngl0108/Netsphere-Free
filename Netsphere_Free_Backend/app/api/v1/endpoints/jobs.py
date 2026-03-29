from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.models.user import User

router = APIRouter()


@router.get("/{task_id}")
def get_task_status(task_id: str, current_user: User = Depends(deps.require_viewer)):
    try:
        from celery.result import AsyncResult
        import celery_app
    except Exception:
        raise HTTPException(status_code=503, detail="Celery is not available")

    r = AsyncResult(task_id, app=celery_app.celery_app)
    payload = {
        "task_id": task_id,
        "state": r.state,
        "ready": bool(r.ready()),
        "successful": bool(r.successful()) if r.ready() else False,
        "result": r.result if r.ready() else None,
    }
    if r.failed():
        payload["error"] = str(r.result)
    return payload

