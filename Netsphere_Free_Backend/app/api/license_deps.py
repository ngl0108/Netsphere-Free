from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import get_db
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.license_service import LicenseService
from app.services.preview_managed_node_service import PreviewManagedNodeService

_POLICY_BLOCK_PREFIX = "Feature blocked by product policy"


@dataclass(frozen=True)
class ScopePolicy:
    feature: str | None = None
    required_mode: str | None = None


SCOPE_POLICY_MAP: dict[str, ScopePolicy] = {
    "compliance": ScopePolicy(feature="compliance"),
    "cloud": ScopePolicy(feature="cloud"),
    "ztp": ScopePolicy(feature="ztp"),
    "fabric": ScopePolicy(feature="fabric"),
    "automation_hub": ScopePolicy(feature="automation_hub"),
    "images": ScopePolicy(feature="images"),
    "policies": ScopePolicy(feature="policy"),
    "visual": ScopePolicy(feature="visual_config"),
    "traffic": ScopePolicy(feature="traffic"),
    "observability": ScopePolicy(feature="observability"),
    "intent": ScopePolicy(feature="intent"),
    "diagnosis": ScopePolicy(feature="diagnosis"),
    "ops": ScopePolicy(feature="ops"),
}

_FEATURE_ALIASES: dict[str, set[str]] = {
    "policy": {"policies"},
    "policies": {"policy"},
    "visual": {"visual_config"},
    "visual_config": {"visual"},
    "automation_hub": {"automation_hub", "automation"},
}


def _normalize_feature(value: str | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"multicloud_full", "hybrid_cloud"}:
        return "multicloud_full"
    return "wan_segment_only"


def _get_product_mode(db: Session) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == "product_operating_mode").first()
    raw = row.value if row and row.value is not None else "wan_segment_only"
    return _normalize_mode(str(raw))


def _require_policy(block_reason: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"{_POLICY_BLOCK_PREFIX}: {block_reason}",
    )


def _feature_candidates(feature: str) -> set[str]:
    base = _normalize_feature(feature)
    out = {base}
    out.update(_FEATURE_ALIASES.get(base, set()))
    for k, aliases in _FEATURE_ALIASES.items():
        if base in aliases:
            out.add(k)
    return {_normalize_feature(x) for x in out}


def require_product_mode(required_mode: str) -> Callable:
    required_norm = _normalize_mode(required_mode)

    def _dep(
        db: Session = Depends(get_db),
        current_user: User = Depends(deps.require_operator),
    ) -> bool:
        current_mode = _get_product_mode(db)
        if current_mode == required_norm:
            return True
        _require_policy(f"requires mode '{required_norm}' (current: '{current_mode}')")
        return False

    return _dep


def require_license_feature(feature: str) -> Callable:
    feature_norm = _normalize_feature(feature)
    accepted = _feature_candidates(feature_norm)

    def _dep(
        db: Session = Depends(get_db),
        current_user: User = Depends(deps.require_operator),
    ) -> bool:
        if feature_norm in {"observability", "diagnosis"} and PreviewManagedNodeService.is_preview_managed_quota_enabled(db):
            return True
        lic = LicenseService.get_effective_license(db)
        if not lic or not lic.is_valid:
            _require_policy(f"valid license required for '{feature_norm}'")
        feats = {_normalize_feature(x) for x in (lic.features or [])}
        if "all" in feats or feats.intersection(accepted):
            return True
        _require_policy(f"license does not include '{feature_norm}'")
        return False

    return _dep


def require_feature_access(feature: str, *, required_mode: str | None = None) -> Callable:
    feature_dep = require_license_feature(feature)
    mode_dep = require_product_mode(required_mode) if required_mode else None

    def _dep(
        db: Session = Depends(get_db),
        current_user: User = Depends(deps.require_operator),
    ) -> bool:
        feature_dep(db=db, current_user=current_user)
        if mode_dep:
            mode_dep(db=db, current_user=current_user)
        return True

    return _dep


def scope_dependencies(scope: str) -> list:
    policy = SCOPE_POLICY_MAP.get(_normalize_feature(scope))
    if not policy:
        return []
    if policy.feature:
        return [Depends(require_feature_access(policy.feature, required_mode=policy.required_mode))]
    if policy.required_mode:
        return [Depends(require_product_mode(policy.required_mode))]
    return []
