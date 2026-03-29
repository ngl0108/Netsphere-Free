from fastapi import APIRouter, Depends
from app.api import deps
from app.models.user import User

from app.services.netflow_collector import flow_store

router = APIRouter()


@router.get("/top-talkers")
async def top_talkers(window_sec: int = 300, limit: int = 10, current_user: User = Depends(deps.require_viewer)):
    return await flow_store.top_talkers(window_sec=window_sec, limit=limit)


@router.get("/top-flows")
async def top_flows(window_sec: int = 300, limit: int = 10, current_user: User = Depends(deps.require_viewer)):
    return await flow_store.top_flows(window_sec=window_sec, limit=limit)


@router.get("/top-apps")
async def top_apps(window_sec: int = 300, limit: int = 10, current_user: User = Depends(deps.require_viewer)):
    return await flow_store.top_apps(window_sec=window_sec, limit=limit)


@router.get("/top-app-flows")
async def top_app_flows(app: str, window_sec: int = 300, limit: int = 10, current_user: User = Depends(deps.require_viewer)):
    return await flow_store.top_app_flows(app=app, window_sec=window_sec, limit=limit)
