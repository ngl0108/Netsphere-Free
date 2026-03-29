from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.models.user import User
from app.services.intent_template_service import IntentTemplateService


router = APIRouter()


@router.get("/catalog")
def get_intent_template_catalog(
    current_user: User = Depends(deps.require_operator),
) -> Dict[str, Any]:
    _ = current_user
    return IntentTemplateService.get_catalog()


@router.get("/{template_key}")
def get_intent_template(
    template_key: str,
    current_user: User = Depends(deps.require_operator),
) -> Dict[str, Any]:
    _ = current_user
    template = IntentTemplateService.get_template(template_key)
    if not template:
        raise HTTPException(status_code=404, detail="intent template not found")
    return template
