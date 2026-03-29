from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.license_service import LicenseService
from app.services.preview_edition_service import PreviewEditionService


ROLE_ORDER = {
    "admin": 0,
    "operator": 1,
    "viewer": 2,
}

FEATURE_ALIASES: dict[str, set[str]] = {
    "policy": {"policies"},
    "policies": {"policy"},
    "visual": {"visual_config"},
    "visual_config": {"visual"},
    "automation_hub": {"automation"},
    "automation": {"automation_hub"},
}


@dataclass(frozen=True)
class SurfaceDefinition:
    key: str
    path: str
    required_role: str = "viewer"
    feature: str | None = None
    preview_only: bool = False


SURFACES: tuple[SurfaceDefinition, ...] = (
    SurfaceDefinition("operations_home", "/automation", "operator"),
    SurfaceDefinition("dashboard", "/", "viewer"),
    SurfaceDefinition("topology", "/topology", "viewer"),
    SurfaceDefinition("devices", "/devices", "viewer"),
    SurfaceDefinition("diagnosis", "/diagnosis", "operator", "diagnosis"),
    SurfaceDefinition("notifications", "/notifications", "viewer"),
    SurfaceDefinition("observability", "/observability", "operator", "observability"),
    SurfaceDefinition("wireless", "/wireless", "viewer"),
    SurfaceDefinition("discovery", "/discovery", "operator"),
    SurfaceDefinition("sites", "/sites", "viewer"),
    SurfaceDefinition("cloud_accounts", "/cloud/accounts", "operator", "cloud"),
    SurfaceDefinition("cloud_intents", "/cloud/intents", "operator", "cloud"),
    SurfaceDefinition("approval", "/approval", "operator"),
    SurfaceDefinition("config", "/config", "operator"),
    SurfaceDefinition("policy", "/policy", "operator", "policy"),
    SurfaceDefinition("images", "/images", "operator", "images"),
    SurfaceDefinition("intent_templates", "/intent-templates", "operator"),
    SurfaceDefinition("visual_config", "/visual-config", "operator", "visual_config"),
    SurfaceDefinition("ztp", "/ztp", "operator", "ztp"),
    SurfaceDefinition("fabric", "/fabric", "operator", "fabric"),
    SurfaceDefinition("preventive_checks", "/preventive-checks", "operator"),
    SurfaceDefinition("monitoring_profiles", "/monitoring-profiles", "operator"),
    SurfaceDefinition("source_of_truth", "/source-of-truth", "operator"),
    SurfaceDefinition("state_history", "/state-history", "operator"),
    SurfaceDefinition("service_groups", "/service-groups", "operator"),
    SurfaceDefinition("operations_reports", "/operations-reports", "operator"),
    SurfaceDefinition("compliance", "/compliance", "operator", "compliance"),
    SurfaceDefinition("logs", "/logs", "viewer"),
    SurfaceDefinition("audit", "/audit", "operator"),
    SurfaceDefinition("settings", "/settings", "admin"),
    SurfaceDefinition("users", "/users", "admin"),
    SurfaceDefinition("edition_compare", "/edition/compare", "viewer"),
    SurfaceDefinition("preview_contribute", "/preview/contribute", "admin", preview_only=True),
)

WORKSPACES: tuple[dict[str, Any], ...] = (
    {
        "key": "observe",
        "surface_keys": ("dashboard", "topology", "devices", "diagnosis", "notifications", "observability", "wireless"),
        "primary_surface_keys": ("dashboard", "notifications", "observability"),
    },
    {
        "key": "discover",
        "surface_keys": ("discovery", "devices", "sites", "monitoring_profiles", "source_of_truth"),
        "primary_surface_keys": ("discovery", "devices", "monitoring_profiles"),
    },
    {
        "key": "control",
        "surface_keys": ("cloud_accounts", "cloud_intents", "approval", "config", "policy", "images", "intent_templates", "visual_config", "ztp", "fabric"),
        "primary_surface_keys": ("cloud_intents", "approval", "config"),
    },
    {
        "key": "govern",
        "surface_keys": ("preventive_checks", "service_groups", "operations_reports", "state_history", "compliance", "logs", "audit"),
        "primary_surface_keys": ("operations_reports", "service_groups", "state_history"),
    },
)

SIDEBAR_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "operations",
        "surface_keys": ("operations_home",),
    },
    {
        "key": "observe",
        "surface_keys": ("dashboard", "topology", "notifications", "observability"),
        "workspace_key": "observe",
    },
    {
        "key": "discover",
        "surface_keys": ("discovery", "devices", "monitoring_profiles"),
        "workspace_key": "discover",
    },
    {
        "key": "control",
        "surface_keys": ("cloud_accounts", "cloud_intents", "approval", "config"),
        "workspace_key": "control",
    },
    {
        "key": "govern",
        "surface_keys": ("operations_reports", "service_groups", "state_history"),
        "workspace_key": "govern",
    },
    {
        "key": "administration",
        "surface_keys": ("settings", "users"),
    },
    {
        "key": "edition",
        "surface_keys": ("edition_compare",),
    },
)


class PolicyManifestService:
    @staticmethod
    def _block_metadata(code: str) -> dict[str, Any]:
        normalized = str(code or "").strip().lower()
        if normalized == "preview_blocked":
            return {
                "blocked_badge_key": "policy_block_badge_preview",
                "blocked_title_key": "policy_block_title_preview",
                "blocked_hint_key": "policy_block_hint_preview",
                "blocked_action_path": "/edition/compare",
                "blocked_action_label_key": "policy_block_action_compare",
                "blocked_action_desc_key": "policy_block_action_compare_desc",
            }
        if normalized == "license_feature_required":
            return {
                "blocked_badge_key": "policy_block_badge_license",
                "blocked_title_key": "policy_block_title_license",
                "blocked_hint_key": "policy_block_hint_license",
                "blocked_action_path": "/edition/compare",
                "blocked_action_label_key": "policy_block_action_compare",
                "blocked_action_desc_key": "policy_block_action_compare_desc",
            }
        if normalized == "role_required":
            return {
                "blocked_badge_key": "policy_block_badge_role",
                "blocked_title_key": "policy_block_title_role",
                "blocked_hint_key": "policy_block_hint_role",
                "blocked_action_path": "/automation",
                "blocked_action_label_key": "policy_block_action_home",
                "blocked_action_desc_key": "policy_block_action_home_desc",
            }
        if normalized == "preview_only":
            return {
                "blocked_badge_key": "policy_block_badge_free_only",
                "blocked_title_key": "policy_block_title_free_only",
                "blocked_hint_key": "policy_block_hint_free_only",
                "blocked_action_path": "/automation",
                "blocked_action_label_key": "policy_block_action_home",
                "blocked_action_desc_key": "policy_block_action_free_review_desc",
            }
        return {
            "blocked_badge_key": "policy_block_badge_default",
            "blocked_title_key": "app_policy_blocked_title",
            "blocked_hint_key": "app_policy_blocked_hint",
            "blocked_action_path": "/automation",
            "blocked_action_label_key": "policy_block_action_home",
            "blocked_action_desc_key": "policy_block_action_home_desc",
        }

    @classmethod
    def _surface_payload(
        cls,
        *,
        definition: SurfaceDefinition,
        visible: bool,
        navigable: bool,
        executable: bool,
        blocked_code: str = "",
        blocked_reason: str = "",
        upgrade_copy: str = "",
    ) -> dict[str, Any]:
        payload = {
            "path": definition.path,
            "visible": bool(visible),
            "navigable": bool(navigable),
            "executable": bool(executable),
            "blocked_code": str(blocked_code or "").strip().lower(),
            "blocked_reason": blocked_reason,
            "upgrade_copy": upgrade_copy,
        }
        if payload["blocked_code"]:
            payload.update(cls._block_metadata(payload["blocked_code"]))
        return payload

    @staticmethod
    def _normalize_feature(value: str | None) -> str:
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    @classmethod
    def _feature_candidates(cls, feature: str | None) -> set[str]:
        base = cls._normalize_feature(feature)
        if not base:
            return set()
        out = {base}
        out.update(FEATURE_ALIASES.get(base, set()))
        for key, aliases in FEATURE_ALIASES.items():
            if base in aliases:
                out.add(key)
        return {cls._normalize_feature(item) for item in out}

    @staticmethod
    def _normalize_path(raw: str | None) -> str:
        path = str(raw or "").strip() or "/"
        if not path.startswith("/"):
            path = f"/{path}"
        if len(path) > 1:
            path = path.rstrip("/")
        return path or "/"

    @classmethod
    def _matches_prefix(cls, path: str, prefix: str) -> bool:
        normalized_path = cls._normalize_path(path)
        normalized_prefix = cls._normalize_path(prefix)
        if normalized_prefix == "/":
            return normalized_path == "/"
        return normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/")

    @classmethod
    def _is_preview_path_allowed(cls, path: str, policy: dict[str, Any]) -> bool:
        if policy.get("preview_enabled") is not True:
            return True
        normalized = cls._normalize_path(path)
        exact = {cls._normalize_path(item) for item in list(policy.get("allowed_nav_exact_paths") or [])}
        if normalized in exact:
            return True
        return any(cls._matches_prefix(normalized, prefix) for prefix in list(policy.get("allowed_nav_prefixes") or []))

    @staticmethod
    def _role_allows(user_role: str | None, required_role: str) -> bool:
        current = ROLE_ORDER.get(str(user_role or "").strip().lower(), 99)
        required = ROLE_ORDER.get(str(required_role or "").strip().lower(), 99)
        return current <= required

    @classmethod
    def _license_allows(cls, license_payload: dict[str, Any], feature: str | None) -> bool:
        if not feature:
            return True
        if not bool(license_payload.get("is_valid")):
            return False
        features = {
            cls._normalize_feature(item)
            for item in list(license_payload.get("features") or [])
        }
        if "all" in features:
            return True
        return bool(features.intersection(cls._feature_candidates(feature)))

    @classmethod
    def _build_surface_access(
        cls,
        *,
        definition: SurfaceDefinition,
        user: User,
        preview_policy: dict[str, Any],
        license_payload: dict[str, Any],
    ) -> dict[str, Any]:
        role = str(getattr(user, "role", "") or "").strip().lower()
        role_allowed = cls._role_allows(role, definition.required_role)
        preview_enabled = preview_policy.get("preview_enabled") is True

        visible = role_allowed
        navigable = role_allowed
        executable = role_allowed
        blocked_code = ""
        blocked_reason = ""
        upgrade_copy = ""

        if definition.preview_only:
            visible = role_allowed and preview_enabled
            navigable = visible
            executable = visible
            if role_allowed and not preview_enabled:
                blocked_code = "preview_only"
                blocked_reason = "This surface is available only in NetSphere Free."
            return cls._surface_payload(
                definition=definition,
                visible=visible,
                navigable=navigable,
                executable=executable,
                blocked_code=blocked_code,
                blocked_reason=blocked_reason,
                upgrade_copy=upgrade_copy,
            )

        if not role_allowed:
            return cls._surface_payload(
                definition=definition,
                visible=False,
                navigable=False,
                executable=False,
                blocked_code="role_required",
                blocked_reason=f"Requires {definition.required_role} role.",
                upgrade_copy="",
            )

        if preview_enabled and not cls._is_preview_path_allowed(definition.path, preview_policy):
            return cls._surface_payload(
                definition=definition,
                visible=False,
                navigable=False,
                executable=False,
                blocked_code="preview_blocked",
                blocked_reason="This surface is disabled in NetSphere Free.",
                upgrade_copy="Upgrade to Pro to unlock this operating surface.",
            )

        feature_norm = cls._normalize_feature(definition.feature)
        preview_feature_allowed = preview_enabled and feature_norm in {"observability", "diagnosis"}

        if definition.feature and not preview_feature_allowed and not cls._license_allows(license_payload, definition.feature):
            return cls._surface_payload(
                definition=definition,
                visible=True,
                navigable=False,
                executable=False,
                blocked_code="license_feature_required",
                blocked_reason=f"Valid license required for '{cls._normalize_feature(definition.feature)}'.",
                upgrade_copy="Enable the matching Pro capability to open this workflow.",
            )

        return cls._surface_payload(
            definition=definition,
            visible=True,
            navigable=True,
            executable=True,
        )

    @classmethod
    def build(cls, db: Session, user: User) -> dict[str, Any]:
        preview_policy = PreviewEditionService.get_policy(db)
        license_payload = LicenseService.get_status(db)
        surfaces = {
            definition.key: cls._build_surface_access(
                definition=definition,
                user=user,
                preview_policy=preview_policy,
                license_payload=license_payload,
            )
            for definition in SURFACES
        }
        workspaces = []
        for workspace in WORKSPACES:
            visible_keys = [
                key
                for key in list(workspace.get("surface_keys") or [])
                if surfaces.get(key, {}).get("visible") is True
            ]
            if not visible_keys:
                continue
            workspaces.append(
                {
                    "key": str(workspace.get("key") or "").strip(),
                    "surface_keys": visible_keys,
                    "primary_surface_keys": [
                        key
                        for key in list(workspace.get("primary_surface_keys") or [])
                        if key in visible_keys
                    ],
                }
            )

        sidebar_sections = []
        for section in SIDEBAR_SECTIONS:
            navigable_keys = [
                key
                for key in list(section.get("surface_keys") or [])
                if surfaces.get(key, {}).get("visible") is True and surfaces.get(key, {}).get("navigable") is True
            ]
            if not navigable_keys:
                continue
            sidebar_sections.append(
                {
                    "key": str(section.get("key") or "").strip(),
                    "workspace_key": str(section.get("workspace_key") or "").strip() or None,
                    "surface_keys": navigable_keys,
                }
            )

        return {
            "preview_enabled": bool(preview_policy.get("preview_enabled")),
            "edition": "free" if bool(preview_policy.get("preview_enabled")) else "pro",
            "role": str(getattr(user, "role", "") or "").strip().lower() or "viewer",
            "license": {
                "is_valid": bool(license_payload.get("is_valid")),
                "features": list(license_payload.get("features") or []),
                "status": str(license_payload.get("status") or ""),
            },
            "preview_policy": {
                "managed_node_limit": preview_policy.get("managed_node_limit"),
                "managed_nodes": preview_policy.get("managed_nodes") or {},
                "blocked_features": list(preview_policy.get("blocked_features") or []),
                "experience_pillars": list(preview_policy.get("experience_pillars") or []),
                "upload_locked": bool(preview_policy.get("upload_locked")),
                "contribution_scope": str(preview_policy.get("contribution_scope") or ""),
            },
            "workspaces": workspaces,
            "navigation": {
                "sidebar_sections": sidebar_sections,
            },
            "surfaces": surfaces,
        }
