from __future__ import annotations

import copy
import json
import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse
from uuid import uuid4

import requests
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.preview_collector_registration import PreviewCollectorRegistration
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.ssh_service import DeviceConnection, DeviceInfo


@dataclass
class _MaskContext:
    ip_map: Dict[str, str] = field(default_factory=dict)
    mac_map: Dict[str, str] = field(default_factory=dict)
    email_map: Dict[str, str] = field(default_factory=dict)
    serial_map: Dict[str, str] = field(default_factory=dict)
    host_map: Dict[str, str] = field(default_factory=dict)
    url_map: Dict[str, str] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=lambda: {
        "ip": 0,
        "mac": 0,
        "email": 0,
        "serial": 0,
        "host": 0,
        "url": 0,
        "secret_lines": 0,
        "certificate_blocks": 0,
    })

    def token(self, category: str, value: str, prefix: str) -> str:
        target = getattr(self, f"{category}_map")
        key = str(value or "").strip()
        if not key:
            return key
        if key not in target:
            idx = len(target) + 1
            target[key] = f"{prefix}_{idx:03d}"
            self.counters[category] = len(target)
        return target[key]


class PreviewEditionService:
    EDITION_ENV_KEY = "NETSPHERE_EDITION"
    SETTING_EDITION_KEY = "product_edition"
    SETTING_CAPTURE_ENABLED_KEY = "preview_capture_enabled"
    SETTING_UPLOAD_ENABLED_KEY = "preview_contribution_upload_enabled"
    SETTING_UPLOAD_OPT_IN_REQUIRED_KEY = "preview_contribution_opt_in_required"
    SETTING_UPLOAD_PARTICIPATION_KEY = "preview_contribution_participation"
    SETTING_UPLOAD_PARTICIPATION_RECORDED_AT_KEY = "preview_contribution_participation_recorded_at"
    SETTING_UPLOAD_PARTICIPATION_ACTOR_KEY = "preview_contribution_participation_actor"
    SETTING_UPLOAD_LOCKED_KEY = "preview_contribution_locked"
    SETTING_UPLOAD_CHANGE_REQUIRES_RESET_KEY = "preview_contribution_change_requires_reset"
    SETTING_UPLOAD_SCOPE_KEY = "preview_contribution_scope"
    SETTING_REQUIRE_CONSENT_KEY = "preview_contribution_require_consent"
    SETTING_ALLOW_DEVICE_CAPTURE_KEY = "preview_allow_device_capture"
    SETTING_ALLOWED_COMMANDS_KEY = "preview_collection_allowed_commands_json"
    SETTING_STORAGE_DIR_KEY = "preview_contribution_storage_dir"
    SETTING_DEPLOYMENT_ROLE_KEY = "preview_deployment_role"
    SETTING_UPLOAD_TARGET_MODE_KEY = "preview_upload_target_mode"
    SETTING_REMOTE_UPLOAD_URL_KEY = "preview_remote_upload_url"
    SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY = "preview_remote_upload_client_id"
    SETTING_REMOTE_UPLOAD_TOKEN_KEY = "preview_remote_upload_token"
    SETTING_REMOTE_UPLOAD_TIMEOUT_SECONDS_KEY = "preview_remote_upload_timeout_seconds"
    SETTING_ACCEPT_REMOTE_UPLOADS_KEY = "preview_accept_remote_uploads"
    SETTING_LOCAL_EMBEDDED_EXECUTION_KEY = "preview_local_embedded_execution"
    SETTING_SELF_REGISTRATION_ENABLED_KEY = "preview_self_registration_enabled"
    SETTING_INSTALLATION_ID_KEY = "preview_installation_id"
    SETTING_REMOTE_UPLOAD_REGISTERED_AT_KEY = "preview_remote_upload_registered_at"
    SETTING_REMOTE_UPLOAD_REGISTRATION_SOURCE_KEY = "preview_remote_upload_registration_source"
    SETTING_REMOTE_UPLOAD_REGISTRATION_STATE_KEY = "preview_remote_upload_registration_state"
    SETTING_REMOTE_UPLOAD_REGISTRATION_ERROR_KEY = "preview_remote_upload_registration_error"
    SETTING_INITIAL_ADMIN_INITIALIZED_KEY = "preview_initial_admin_initialized"
    SETTING_INITIAL_ADMIN_CREATED_AT_KEY = "preview_initial_admin_created_at"
    SETTING_INITIAL_ADMIN_USERNAME_KEY = "preview_initial_admin_username"
    SELF_REGISTRATION_ISSUED_TO_PREFIX = "self_install:"
    DEFAULT_CONTRIBUTION_SCOPE = "allowlisted_read_only_commands_only"

    DEFAULT_ALLOWED_COMMANDS = [
        "show version",
        "display version",
        "get system status",
        "show inventory",
        "show chassis hardware",
        "display device",
        "show interfaces brief",
        "show interfaces status",
        "show interfaces terse",
        "display interface brief",
        "show vlan",
        "display vlan",
        "show mac address-table",
        "display mac-address",
        "show lldp neighbors detail",
        "show cdp neighbors detail",
        "display lldp neighbor-information verbose",
        "show ip route summary",
        "show route summary",
        "display ip routing-table statistics",
        "show ospf neighbor",
        "show ip ospf neighbor",
        "display ospf peer",
        "show bgp summary",
        "show ip bgp summary",
        "display bgp peer",
        "show evpn summary",
        "show bgp evpn summary",
        "show vxlan vni",
        "show nve peers",
        "show system info",
    ]

    DEFAULT_BLOCKED_COMMAND_PREFIXES = [
        "show running-config",
        "show startup-config",
        "show configuration",
        "display current-configuration",
        "display saved-configuration",
        "more system:running-config",
        "show full-configuration",
        "tmsh list",
        "show users",
        "show aaa",
        "show tacacs",
        "show radius",
        "show crypto",
        "show vpn",
        "show nat session",
    ]

    BLOCKED_MUTATION_PREFIXES = [
        "/api/v1/settings",
        "/api/v1/auth/users",
        "/api/v1/license",
        "/api/v1/support/restore",
        "/api/v1/sdn/images",
        "/api/v1/sdn/policies",
        "/api/v1/approval",
        "/api/v1/fabric",
        "/api/v1/visual",
        "/api/v1/cloud",
        "/api/v1/ztp",
        "/api/v1/intent",
    ]

    BLOCKED_MUTATION_EXACT = {
        "/api/v1/ops/observability",
    }

    BLOCKED_MUTATION_CONTAINS = [
        "/compliance/drift/remediate",
        "/compliance/drift/remediate-batch",
        "/automation/run",
        "/deploy",
        "/rollback",
    ]

    ALLOWED_MUTATION_PREFIXES = [
        "/api/v1/auth/login",
        "/api/v1/auth/bootstrap",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/devices",
        "/api/v1/sites",
        "/api/v1/discovery",
        "/api/v1/topology",
        "/api/v1/diagnosis",
        "/api/v1/sdn/issues",
        "/api/v1/preview",
    ]

    ALLOWED_NAV_EXACT_PATHS = [
        "/",
        "/topology",
        "/devices",
        "/sites",
        "/diagnosis",
        "/notifications",
        "/wireless",
        "/discovery",
        "/automation",
        "/observability",
        "/edition/compare",
        "/logs",
        "/audit",
        "/preview/contribute",
    ]

    ALLOWED_NAV_PREFIXES = [
        "/devices",
    ]

    EXPERIENCE_PILLARS = [
        {
            "key": "auto_discovery",
            "route": "/discovery",
            "surface": "discovery",
        },
        {
            "key": "auto_topology",
            "route": "/topology",
            "surface": "topology",
        },
        {
            "key": "connected_nms",
            "route": "/devices",
            "surface": "nms",
        },
    ]
    _POLICY_CACHE_TTL_SECONDS = max(int(os.getenv("PREVIEW_POLICY_CACHE_TTL_SECONDS", "5") or 5), 1)
    _policy_cache_lock = Lock()
    _policy_cache_expires_at = 0.0
    _policy_cache_payload: Dict[str, Any] | None = None

    _IPV4_RE = re.compile(r"\b(?:(?:\d{1,3})\.){3}(?:\d{1,3})\b")
    _IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{1,4}\b")
    _MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
    _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
    _URL_RE = re.compile(r"\bhttps?://[^\s\"']+\b", re.IGNORECASE)
    _CERT_BLOCK_RE = re.compile(
        r"-----BEGIN [^-]+-----.*?-----END [^-]+-----",
        re.DOTALL,
    )
    _SECRET_LINE_RE = re.compile(
        r"(?im)^([^\n\r#]*?\b(?:password|secret|community|string|token|api[_ -]?key|private[_ -]?key|auth[_ -]?key|priv[_ -]?key)\b[^\n\r:=]*?[:=]?\s*)(\S+)(.*)$"
    )
    _SERIAL_INLINE_RE = re.compile(
        r"(?im)\b(?:serial(?:\s+number)?|processor board id|system serial number|sn)\b\s*[:#]?\s*([A-Za-z0-9._/-]{4,})"
    )
    _HOSTNAME_LINE_RE = re.compile(
        r"(?im)^(hostname|set system host-name|sysname)\s+([A-Za-z0-9._-]+)\s*$"
    )

    class RemoteUploadError(RuntimeError):
        pass

    @classmethod
    def _backend_root(cls) -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _storage_dir(cls, db: Session | None = None) -> Path:
        configured = os.getenv(cls.SETTING_STORAGE_DIR_KEY.upper())
        if not configured and db is not None:
            row = db.query(SystemSetting).filter(SystemSetting.key == cls.SETTING_STORAGE_DIR_KEY).first()
            configured = str(row.value).strip() if row and row.value else ""
        if configured:
            path = Path(configured)
            return path if path.is_absolute() else (cls._backend_root() / path)
        return cls._backend_root() / "preview_contributions"

    @staticmethod
    def _normalize_command(command: str) -> str:
        return " ".join(str(command or "").strip().lower().split())

    @staticmethod
    def _read_settings(db: Session, keys: Iterable[str]) -> Dict[str, str]:
        rows = db.query(SystemSetting).filter(SystemSetting.key.in_(list(keys))).all()
        return {str(row.key): str(row.value or "") for row in rows}

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return bool(default)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _json_list(value: Any, default: List[str]) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return list(default)
        try:
            parsed = json.loads(raw)
        except Exception:
            return list(default)
        if not isinstance(parsed, list):
            return list(default)
        return [str(item).strip() for item in parsed if str(item).strip()]

    @staticmethod
    def _resolve_setting(values: Dict[str, str], key: str, default: str = "") -> str:
        env_value = os.getenv(str(key or "").upper())
        if env_value is not None and str(env_value).strip():
            return str(env_value).strip()
        raw = values.get(str(key), default)
        return str(raw or default).strip()

    @staticmethod
    def _normalize_deployment_role(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"collector", "collector_installed", "installed_collector", "local_collector"}:
            return "collector_installed"
        if raw in {"intake", "intake_server", "remote_intake", "central_intake"}:
            return "intake_server"
        return "standalone"

    @staticmethod
    def _normalize_upload_target_mode(value: Any, deployment_role: str) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"local_only", "remote_only", "dual_write"}:
            return raw
        if deployment_role == "collector_installed":
            return "remote_only"
        return "local_only"

    @staticmethod
    def _normalize_remote_upload_url(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        path = str(parsed.path or "").rstrip("/")
        if not path:
            return raw.rstrip("/") + "/api/v1/preview/contributions"
        return raw

    @staticmethod
    def _display_remote_destination(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        return str(parsed.netloc or parsed.path or "").strip()

    @staticmethod
    def _normalize_upload_participation(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"enabled", "opted_in", "opt_in", "on", "true", "yes"}:
            return "enabled"
        if raw in {"disabled", "opted_out", "opt_out", "off", "false", "no", "declined"}:
            return "disabled"
        return "unset"

    @staticmethod
    def _hash_registration_token(token: str) -> str:
        return hashlib.sha256(str(token or "").strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _new_registration_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def _new_collector_id() -> str:
        return f"pvc-{uuid4().hex[:16]}"

    @staticmethod
    def _token_hint(token: str) -> str:
        raw = str(token or "").strip()
        if len(raw) <= 6:
            return raw
        return f"...{raw[-6:]}"

    @staticmethod
    def _upsert_setting(
        db: Session,
        *,
        key: str,
        value: Any,
        description: str,
        category: str = "preview",
    ) -> SystemSetting:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        if row is None:
            row = SystemSetting(
                key=str(key),
                value=str(value or ""),
                description=str(description or key),
                category=str(category or "preview"),
            )
            db.add(row)
        else:
            row.value = str(value or "")
            if description:
                row.description = str(description)
            if category:
                row.category = str(category)
        PreviewEditionService.invalidate_policy_cache()
        return row

    @classmethod
    def invalidate_policy_cache(cls) -> None:
        with cls._policy_cache_lock:
            cls._policy_cache_payload = None
            cls._policy_cache_expires_at = 0.0

    @staticmethod
    def _policy_cache_enabled() -> bool:
        return not bool(os.getenv("PYTEST_CURRENT_TEST"))

    @classmethod
    def _get_cached_policy(cls) -> Dict[str, Any] | None:
        if not cls._policy_cache_enabled():
            return None
        now = time.time()
        with cls._policy_cache_lock:
            if cls._policy_cache_payload is None or now >= cls._policy_cache_expires_at:
                return None
            return copy.deepcopy(cls._policy_cache_payload)

    @classmethod
    def _set_cached_policy(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not cls._policy_cache_enabled():
            return payload
        now = time.time()
        cached_payload = copy.deepcopy(payload)
        with cls._policy_cache_lock:
            cls._policy_cache_payload = cached_payload
            cls._policy_cache_expires_at = now + cls._POLICY_CACHE_TTL_SECONDS
        return copy.deepcopy(cached_payload)

    @classmethod
    def _human_user_query(cls, db: Session):
        return db.query(User).filter(User.username != "system")

    @classmethod
    def initial_admin_allowed(cls, db: Session) -> bool:
        policy = cls.get_policy(db)
        return bool(policy.get("preview_enabled"))

    @classmethod
    def initial_admin_initialized(cls, db: Session) -> bool:
        values = cls._read_settings(db, [cls.SETTING_INITIAL_ADMIN_INITIALIZED_KEY])
        return cls._as_bool(values.get(cls.SETTING_INITIAL_ADMIN_INITIALIZED_KEY), False)

    @classmethod
    def initial_admin_required(cls, db: Session) -> bool:
        if not cls.initial_admin_allowed(db):
            return False
        if cls.initial_admin_initialized(db):
            return False
        return cls._human_user_query(db).count() == 0

    @classmethod
    def mark_initial_admin_initialized(cls, db: Session, *, user: User) -> None:
        now = datetime.now(timezone.utc).isoformat()
        cls._upsert_setting(
            db,
            key=cls.SETTING_INITIAL_ADMIN_INITIALIZED_KEY,
            value="true",
            description="Preview initial admin bootstrap has been completed",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_INITIAL_ADMIN_CREATED_AT_KEY,
            value=now,
            description="When the preview initial admin was created",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_INITIAL_ADMIN_USERNAME_KEY,
            value=str(getattr(user, "username", "") or "").strip(),
            description="Username of the preview initial admin",
        )
        db.commit()

    @classmethod
    def _normalize_installation_id(cls, value: Any) -> str:
        raw = str(value or "").strip().lower()
        clean = re.sub(r"[^a-z0-9._:-]", "", raw)
        return clean[:96]

    @classmethod
    def _self_registration_issued_to(cls, installation_id: str) -> str:
        return f"{cls.SELF_REGISTRATION_ISSUED_TO_PREFIX}{cls._normalize_installation_id(installation_id)}"

    @classmethod
    def get_or_create_installation_id(cls, db: Session) -> str:
        values = cls._read_settings(db, [cls.SETTING_INSTALLATION_ID_KEY])
        current = cls._normalize_installation_id(values.get(cls.SETTING_INSTALLATION_ID_KEY))
        if current:
            return current
        generated = f"pvi-{uuid4().hex}"
        cls._upsert_setting(
            db,
            key=cls.SETTING_INSTALLATION_ID_KEY,
            value=generated,
            description="Stable preview collector installation identifier",
        )
        db.commit()
        return generated

    @classmethod
    def _default_self_registration_label(cls, installation_id: str) -> str:
        suffix = str(installation_id or "").strip()[-6:].upper() or uuid4().hex[:6].upper()
        return f"Preview Collector {suffix}"

    @classmethod
    def _derive_remote_enrollment_url(cls, remote_upload_url: Any) -> str:
        normalized = cls._normalize_remote_upload_url(remote_upload_url)
        if not normalized:
            return ""
        if normalized.endswith("/api/v1/preview/contributions"):
            return normalized[: -len("/contributions")] + "/intake-enroll"
        parsed = urlparse(normalized)
        if not parsed.scheme or not parsed.netloc:
            return ""
        path = str(parsed.path or "").rstrip("/")
        if not path:
            return normalized.rstrip("/") + "/api/v1/preview/intake-enroll"
        return f"{normalized.rstrip('/')}/intake-enroll"

    @classmethod
    def _remote_public_upload_url(cls) -> str:
        base = str(os.getenv("PREVIEW_PUBLIC_UPLOAD_BASE_URL") or "").strip().rstrip("/")
        if not base:
            return ""
        return f"{base}/api/v1/preview/contributions"

    @classmethod
    def _store_remote_upload_registration(
        cls,
        db: Session,
        *,
        collector_id: str,
        intake_token: str,
        source: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY,
            value=str(collector_id or "").strip(),
            description="Preview remote upload collector identifier",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_TOKEN_KEY,
            value=str(intake_token or "").strip(),
            description="Preview remote upload collector token",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTERED_AT_KEY,
            value=now,
            description="When preview remote upload credentials were last issued",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_SOURCE_KEY,
            value=str(source or "").strip() or "auto_enroll",
            description="How preview remote upload credentials were issued",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_STATE_KEY,
            value="registered",
            description="Current preview remote upload registration state",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_ERROR_KEY,
            value="",
            description="Last preview remote upload registration error",
        )
        db.commit()

    @classmethod
    def _mark_remote_upload_registration_error(cls, db: Session, *, error: str, source: str) -> None:
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_SOURCE_KEY,
            value=str(source or "").strip() or "auto_enroll",
            description="How preview remote upload credentials were issued",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_STATE_KEY,
            value="failed",
            description="Current preview remote upload registration state",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_REMOTE_UPLOAD_REGISTRATION_ERROR_KEY,
            value=str(error or "").strip(),
            description="Last preview remote upload registration error",
        )
        db.commit()

    @classmethod
    def _registration_to_dict(cls, registration: PreviewCollectorRegistration) -> Dict[str, Any]:
        return {
            "collector_id": str(registration.collector_id or ""),
            "label": str(registration.label or ""),
            "issued_to": str(registration.issued_to or ""),
            "notes": str(registration.notes or ""),
            "token_hint": str(registration.token_hint or ""),
            "is_active": bool(registration.is_active),
            "created_by": str(registration.created_by or ""),
            "created_at": registration.created_at.isoformat() if registration.created_at else "",
            "updated_at": registration.updated_at.isoformat() if registration.updated_at else "",
            "last_used_at": registration.last_used_at.isoformat() if registration.last_used_at else "",
            "revoked_at": registration.revoked_at.isoformat() if registration.revoked_at else "",
        }

    @classmethod
    def list_intake_registrations(cls, db: Session) -> List[Dict[str, Any]]:
        rows = (
            db.query(PreviewCollectorRegistration)
            .order_by(PreviewCollectorRegistration.created_at.desc(), PreviewCollectorRegistration.id.desc())
            .all()
        )
        return [cls._registration_to_dict(row) for row in rows]

    @classmethod
    def create_intake_registration(
        cls,
        db: Session,
        *,
        label: str,
        issued_to: str = "",
        notes: str = "",
        created_by: str = "",
    ) -> Dict[str, Any]:
        clean_label = str(label or "").strip()
        if not clean_label:
            raise ValueError("Registration label is required.")
        collector_id = cls._new_collector_id()
        token = cls._new_registration_token()
        row = PreviewCollectorRegistration(
            collector_id=collector_id,
            label=clean_label,
            issued_to=str(issued_to or "").strip(),
            notes=str(notes or "").strip(),
            token_hash=cls._hash_registration_token(token),
            token_hint=cls._token_hint(token),
            is_active=True,
            created_by=str(created_by or "").strip(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "registration": cls._registration_to_dict(row),
            "collector_id": collector_id,
            "intake_token": token,
        }

    @classmethod
    def rotate_intake_registration(
        cls,
        db: Session,
        *,
        collector_id: str,
        notes: str = "",
        rotated_by: str = "",
    ) -> Dict[str, Any]:
        row = (
            db.query(PreviewCollectorRegistration)
            .filter(PreviewCollectorRegistration.collector_id == str(collector_id or "").strip())
            .first()
        )
        if row is None:
            raise ValueError("Collector registration not found.")
        token = cls._new_registration_token()
        row.token_hash = cls._hash_registration_token(token)
        row.token_hint = cls._token_hint(token)
        row.is_active = True
        row.revoked_at = None
        if notes:
            row.notes = str(notes).strip()
        if rotated_by:
            row.created_by = str(rotated_by).strip()
        db.commit()
        db.refresh(row)
        return {
            "registration": cls._registration_to_dict(row),
            "collector_id": row.collector_id,
            "intake_token": token,
        }

    @classmethod
    def revoke_intake_registration(cls, db: Session, *, collector_id: str) -> Dict[str, Any]:
        row = (
            db.query(PreviewCollectorRegistration)
            .filter(PreviewCollectorRegistration.collector_id == str(collector_id or "").strip())
            .first()
        )
        if row is None:
            raise ValueError("Collector registration not found.")
        row.is_active = False
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return cls._registration_to_dict(row)

    @classmethod
    def self_enroll_intake_registration(
        cls,
        db: Session,
        *,
        installation_id: str,
        requested_label: str = "",
        source: str = "collector_auto_enroll",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        policy = cls.get_policy(db)
        if not policy.get("accept_remote_uploads"):
            raise PermissionError("Preview intake self-registration is disabled.")
        if not policy.get("self_registration_enabled"):
            raise PermissionError("Preview intake self-registration is disabled.")

        clean_installation_id = cls._normalize_installation_id(installation_id)
        if not clean_installation_id:
            raise ValueError("A valid installation_id is required.")

        issued_to = cls._self_registration_issued_to(clean_installation_id)
        clean_label = str(requested_label or "").strip() or cls._default_self_registration_label(clean_installation_id)
        note_payload = {
            "source": str(source or "").strip() or "collector_auto_enroll",
            "metadata": dict(metadata or {}),
        }
        serialized_notes = json.dumps(note_payload, ensure_ascii=False, separators=(",", ":"))
        token = cls._new_registration_token()
        row = (
            db.query(PreviewCollectorRegistration)
            .filter(PreviewCollectorRegistration.issued_to == issued_to)
            .order_by(PreviewCollectorRegistration.id.desc())
            .first()
        )

        if row is None:
            row = PreviewCollectorRegistration(
                collector_id=cls._new_collector_id(),
                label=clean_label,
                issued_to=issued_to,
                notes=serialized_notes,
                token_hash=cls._hash_registration_token(token),
                token_hint=cls._token_hint(token),
                is_active=True,
                created_by="self_enroll",
            )
            db.add(row)
        else:
            row.label = clean_label
            row.notes = serialized_notes
            row.token_hash = cls._hash_registration_token(token)
            row.token_hint = cls._token_hint(token)
            row.is_active = True
            row.revoked_at = None
            row.created_by = "self_enroll"

        db.commit()
        db.refresh(row)
        return {
            "registration": cls._registration_to_dict(row),
            "collector_id": str(row.collector_id or ""),
            "intake_token": token,
            "upload_url": cls._remote_public_upload_url(),
            "issued_via": "self_enroll",
        }

    @classmethod
    def get_policy(cls, db: Session) -> Dict[str, Any]:
        cached = cls._get_cached_policy()
        if cached is not None:
            return cached
        keys = [
            cls.SETTING_EDITION_KEY,
            cls.SETTING_CAPTURE_ENABLED_KEY,
            cls.SETTING_UPLOAD_ENABLED_KEY,
            cls.SETTING_UPLOAD_OPT_IN_REQUIRED_KEY,
            cls.SETTING_UPLOAD_PARTICIPATION_KEY,
            cls.SETTING_UPLOAD_PARTICIPATION_RECORDED_AT_KEY,
            cls.SETTING_UPLOAD_PARTICIPATION_ACTOR_KEY,
            cls.SETTING_UPLOAD_LOCKED_KEY,
            cls.SETTING_UPLOAD_CHANGE_REQUIRES_RESET_KEY,
            cls.SETTING_UPLOAD_SCOPE_KEY,
            cls.SETTING_REQUIRE_CONSENT_KEY,
            cls.SETTING_ALLOW_DEVICE_CAPTURE_KEY,
            cls.SETTING_ALLOWED_COMMANDS_KEY,
            cls.SETTING_STORAGE_DIR_KEY,
            cls.SETTING_DEPLOYMENT_ROLE_KEY,
            cls.SETTING_UPLOAD_TARGET_MODE_KEY,
            cls.SETTING_REMOTE_UPLOAD_URL_KEY,
            cls.SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY,
            cls.SETTING_REMOTE_UPLOAD_TOKEN_KEY,
            cls.SETTING_REMOTE_UPLOAD_TIMEOUT_SECONDS_KEY,
            cls.SETTING_ACCEPT_REMOTE_UPLOADS_KEY,
            cls.SETTING_LOCAL_EMBEDDED_EXECUTION_KEY,
            cls.SETTING_SELF_REGISTRATION_ENABLED_KEY,
            cls.SETTING_INSTALLATION_ID_KEY,
            cls.SETTING_REMOTE_UPLOAD_REGISTERED_AT_KEY,
            cls.SETTING_REMOTE_UPLOAD_REGISTRATION_SOURCE_KEY,
            cls.SETTING_REMOTE_UPLOAD_REGISTRATION_STATE_KEY,
            cls.SETTING_REMOTE_UPLOAD_REGISTRATION_ERROR_KEY,
        ]
        values = cls._read_settings(db, keys)
        edition = cls._resolve_setting(values, cls.SETTING_EDITION_KEY, os.getenv(cls.EDITION_ENV_KEY) or "enterprise").lower()
        preview_enabled = edition == "preview"
        allowed_commands = cls._json_list(
            values.get(cls.SETTING_ALLOWED_COMMANDS_KEY),
            cls.DEFAULT_ALLOWED_COMMANDS,
        )
        deployment_role = cls._normalize_deployment_role(
            cls._resolve_setting(values, cls.SETTING_DEPLOYMENT_ROLE_KEY, "standalone")
        )
        upload_feature_available = cls._as_bool(values.get(cls.SETTING_UPLOAD_ENABLED_KEY), preview_enabled)
        upload_opt_in_required = cls._as_bool(
            values.get(cls.SETTING_UPLOAD_OPT_IN_REQUIRED_KEY),
            preview_enabled and deployment_role != "intake_server",
        )
        upload_participation = (
            "enabled"
            if deployment_role == "intake_server"
            else cls._normalize_upload_participation(values.get(cls.SETTING_UPLOAD_PARTICIPATION_KEY))
        )
        upload_decision_recorded = upload_participation != "unset"
        upload_opt_in_enabled = upload_participation == "enabled"
        upload_locked = (
            False
            if deployment_role == "intake_server"
            else cls._as_bool(
                cls._resolve_setting(
                    values,
                    cls.SETTING_UPLOAD_LOCKED_KEY,
                    "true" if upload_decision_recorded else "false",
                ),
                upload_decision_recorded,
            )
        )
        upload_change_requires_reset = (
            False
            if deployment_role == "intake_server"
            else cls._as_bool(
                cls._resolve_setting(
                    values,
                    cls.SETTING_UPLOAD_CHANGE_REQUIRES_RESET_KEY,
                    "true" if upload_locked else "false",
                ),
                upload_locked,
            )
        )
        contribution_scope = (
            str(
                cls._resolve_setting(
                    values,
                    cls.SETTING_UPLOAD_SCOPE_KEY,
                    cls.DEFAULT_CONTRIBUTION_SCOPE,
                )
            ).strip()
            or cls.DEFAULT_CONTRIBUTION_SCOPE
        )
        upload_target_mode = cls._normalize_upload_target_mode(
            cls._resolve_setting(values, cls.SETTING_UPLOAD_TARGET_MODE_KEY, ""),
            deployment_role,
        )
        remote_upload_url = cls._normalize_remote_upload_url(
            cls._resolve_setting(values, cls.SETTING_REMOTE_UPLOAD_URL_KEY, "")
        )
        remote_upload_client_id = cls._resolve_setting(values, cls.SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY, "")
        remote_upload_token = cls._resolve_setting(values, cls.SETTING_REMOTE_UPLOAD_TOKEN_KEY, "")
        self_registration_enabled = cls._as_bool(
            cls._resolve_setting(
                values,
                cls.SETTING_SELF_REGISTRATION_ENABLED_KEY,
                "true" if preview_enabled else "false",
            ),
            preview_enabled,
        )
        remote_upload_registered = bool(remote_upload_url and remote_upload_client_id and remote_upload_token)
        remote_upload_enabled = upload_target_mode in {"remote_only", "dual_write"} and remote_upload_registered
        accept_remote_uploads = cls._as_bool(
            cls._resolve_setting(values, cls.SETTING_ACCEPT_REMOTE_UPLOADS_KEY, "true" if deployment_role == "intake_server" else "false"),
            deployment_role == "intake_server",
        )
        remote_timeout = cls._resolve_setting(values, cls.SETTING_REMOTE_UPLOAD_TIMEOUT_SECONDS_KEY, "10")
        local_embedded_execution = cls._as_bool(
            cls._resolve_setting(
                values,
                cls.SETTING_LOCAL_EMBEDDED_EXECUTION_KEY,
                "true" if deployment_role == "collector_installed" else "false",
            ),
            deployment_role == "collector_installed",
        )
        effective_upload_enabled = bool(
            upload_feature_available
            and (deployment_role == "intake_server" or not upload_opt_in_required or upload_opt_in_enabled)
        )
        if deployment_role == "intake_server":
            remote_registration_state = "intake_server"
        elif upload_target_mode not in {"remote_only", "dual_write"}:
            remote_registration_state = "local_only"
        elif remote_upload_registered:
            remote_registration_state = "registered"
        elif self_registration_enabled and remote_upload_url:
            remote_registration_state = "pending_registration"
        elif remote_upload_url:
            remote_registration_state = "missing_credentials"
        else:
            remote_registration_state = "missing_remote_url"
        stored_registration_state = cls._resolve_setting(
            values,
            cls.SETTING_REMOTE_UPLOAD_REGISTRATION_STATE_KEY,
            "",
        )
        effective_registration_state = "registered" if remote_upload_registered else (stored_registration_state or remote_registration_state)
        managed_node_limit = None
        managed_summary = None
        if preview_enabled and deployment_role != "intake_server":
            try:
                from app.services.preview_managed_node_service import PreviewManagedNodeService

                PreviewManagedNodeService.reconcile_managed_devices(db)
                managed_node_limit = PreviewManagedNodeService.get_managed_node_limit(db)
                managed_summary = PreviewManagedNodeService.summarize(db)
            except Exception:
                managed_node_limit = 50
                managed_summary = {
                    "managed_limit": 50,
                    "total_discovered": 0,
                    "managed": 0,
                    "discovered_only": 0,
                    "remaining_slots": 50,
                }

        payload = {
            "edition": edition,
            "preview_enabled": preview_enabled,
            "positioning": "experience_preview" if preview_enabled else "enterprise",
            "deployment_role": deployment_role,
            "upload_target_mode": upload_target_mode,
            "local_embedded_execution": local_embedded_execution,
            "capture_enabled": cls._as_bool(values.get(cls.SETTING_CAPTURE_ENABLED_KEY), preview_enabled),
            "upload_enabled": effective_upload_enabled,
            "upload_feature_available": upload_feature_available,
            "upload_opt_in_required": upload_opt_in_required,
            "upload_participation": upload_participation,
            "upload_decision_recorded": upload_decision_recorded,
            "upload_opt_in_enabled": upload_opt_in_enabled,
            "upload_locked": upload_locked,
            "upload_change_requires_reset": upload_change_requires_reset,
            "contribution_scope": contribution_scope,
            "upload_opt_in_recorded_at": cls._resolve_setting(
                values,
                cls.SETTING_UPLOAD_PARTICIPATION_RECORDED_AT_KEY,
                "",
            ),
            "upload_opt_in_actor": cls._resolve_setting(
                values,
                cls.SETTING_UPLOAD_PARTICIPATION_ACTOR_KEY,
                "",
            ),
            "require_consent": cls._as_bool(values.get(cls.SETTING_REQUIRE_CONSENT_KEY), True),
            "allow_device_capture": cls._as_bool(values.get(cls.SETTING_ALLOW_DEVICE_CAPTURE_KEY), True),
            "remote_upload_enabled": remote_upload_enabled,
            "remote_upload_configured": bool(remote_upload_url),
            "remote_upload_registered": remote_upload_registered,
            "remote_upload_client_id": remote_upload_client_id,
            "remote_upload_url": remote_upload_url,
            "remote_upload_destination": cls._display_remote_destination(remote_upload_url),
            "remote_upload_timeout_seconds": remote_timeout,
            "accept_remote_uploads": bool(accept_remote_uploads),
            "self_registration_enabled": bool(self_registration_enabled),
            "installation_id": cls._normalize_installation_id(values.get(cls.SETTING_INSTALLATION_ID_KEY)),
            "remote_upload_registered_at": cls._resolve_setting(
                values,
                cls.SETTING_REMOTE_UPLOAD_REGISTERED_AT_KEY,
                "",
            ),
            "remote_upload_registration_source": cls._resolve_setting(
                values,
                cls.SETTING_REMOTE_UPLOAD_REGISTRATION_SOURCE_KEY,
                "",
            ),
            "remote_upload_registration_state": effective_registration_state,
            "remote_upload_registration_error": cls._resolve_setting(
                values,
                cls.SETTING_REMOTE_UPLOAD_REGISTRATION_ERROR_KEY,
                "",
            ),
            "allowed_commands": allowed_commands,
            "blocked_command_prefixes": list(cls.DEFAULT_BLOCKED_COMMAND_PREFIXES),
            "allowed_nav_exact_paths": list(cls.ALLOWED_NAV_EXACT_PATHS),
            "allowed_nav_prefixes": list(cls.ALLOWED_NAV_PREFIXES),
            "experience_pillars": list(cls.EXPERIENCE_PILLARS),
            "same_codebase_surfaces": [
                "discovery",
                "topology",
                "inventory",
                "diagnosis",
            ],
            "blocked_features": [
                "config_deploy_and_rollback",
                "live_policy_push",
                "software_image_rollout",
                "fabric_and_ztp_execution",
                "compliance_remediation",
                "privileged_admin_and_secret_settings",
                "cloud_bootstrap_and_external_webhooks",
            ],
            "managed_node_limit": managed_node_limit,
            "managed_nodes": managed_summary,
            "contribution_opt_in_model": "mandatory_product_terms_optional_data_sharing",
            "storage_dir_name": cls._storage_dir(db).name,
        }
        return cls._set_cached_policy(payload)

    @classmethod
    def is_preview_enabled(cls, db: Session) -> bool:
        return bool(cls.get_policy(db).get("preview_enabled"))

    @classmethod
    def is_command_allowed(cls, command: str, db: Session | None = None, policy: Dict[str, Any] | None = None) -> bool:
        normalized = cls._normalize_command(command)
        blocked = [cls._normalize_command(item) for item in cls.DEFAULT_BLOCKED_COMMAND_PREFIXES]
        if any(normalized.startswith(prefix) for prefix in blocked):
            return False
        resolved_policy = policy or (cls.get_policy(db) if db is not None else {"allowed_commands": cls.DEFAULT_ALLOWED_COMMANDS})
        allowed = [cls._normalize_command(item) for item in list(resolved_policy.get("allowed_commands") or cls.DEFAULT_ALLOWED_COMMANDS)]
        return normalized in set(allowed)

    @classmethod
    def ensure_commands_allowed(cls, commands: Iterable[str], db: Session | None = None, policy: Dict[str, Any] | None = None) -> List[str]:
        clean = [str(item or "").strip() for item in commands if str(item or "").strip()]
        if not clean:
            clean = list((policy or cls.get_policy(db) if db is not None else {"allowed_commands": cls.DEFAULT_ALLOWED_COMMANDS}).get("allowed_commands") or cls.DEFAULT_ALLOWED_COMMANDS)
        invalid = [cmd for cmd in clean if not cls.is_command_allowed(cmd, db=db, policy=policy)]
        if invalid:
            raise ValueError(f"Commands blocked by preview policy: {', '.join(invalid)}")
        return clean

    @classmethod
    def _replace_tokenized(cls, regex: re.Pattern[str], text: str, ctx: _MaskContext, category: str, prefix: str) -> str:
        def repl(match: re.Match[str]) -> str:
            return ctx.token(category, match.group(0), prefix)

        return regex.sub(repl, text)

    @classmethod
    def _mask_hostname_values(cls, text: str, ctx: _MaskContext, host_candidates: Iterable[str]) -> str:
        def repl(match: re.Match[str]) -> str:
            return f"{match.group(1)} {ctx.token('host', match.group(2), 'HOST')}"

        out = cls._HOSTNAME_LINE_RE.sub(repl, text)
        for value in [str(item).strip() for item in host_candidates if str(item or "").strip()]:
            if not value or value.startswith("HOST_"):
                continue
            pattern = re.compile(rf"\b{re.escape(value)}\b")
            token = ctx.token("host", value, "HOST")
            out = pattern.sub(token, out)
        return out

    @classmethod
    def sanitize_output(
        cls,
        *,
        command: str,
        raw_output: str,
        device: Device | None = None,
        host_candidates: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        text = str(raw_output or "")
        ctx = _MaskContext()

        cert_matches = list(cls._CERT_BLOCK_RE.finditer(text))
        ctx.counters["certificate_blocks"] = len(cert_matches)
        text = cls._CERT_BLOCK_RE.sub("<CERTIFICATE_BLOCK_REDACTED>", text)

        def secret_repl(match: re.Match[str]) -> str:
            ctx.counters["secret_lines"] += 1
            return f"{match.group(1)}<REDACTED_SECRET>{match.group(3)}"

        text = cls._SECRET_LINE_RE.sub(secret_repl, text)

        if device is not None:
            host_candidates = list(host_candidates or []) + [
                getattr(device, "hostname", None),
                getattr(device, "name", None),
                getattr(device, "ip_address", None),
                getattr(device, "serial_number", None),
            ]

        text = cls._mask_hostname_values(text, ctx, host_candidates or [])

        def serial_repl(match: re.Match[str]) -> str:
            return match.group(0).replace(match.group(1), ctx.token("serial", match.group(1), "SERIAL"))

        text = cls._SERIAL_INLINE_RE.sub(serial_repl, text)
        text = cls._replace_tokenized(cls._URL_RE, text, ctx, "url", "URL")
        text = cls._replace_tokenized(cls._EMAIL_RE, text, ctx, "email", "EMAIL")
        text = cls._replace_tokenized(cls._MAC_RE, text, ctx, "mac", "MAC")
        text = cls._replace_tokenized(cls._IPV4_RE, text, ctx, "ip", "IP")
        text = cls._replace_tokenized(cls._IPV6_RE, text, ctx, "ip", "IP")

        return {
            "command": str(command or "").strip(),
            "sanitized_output": text,
            "redaction_summary": dict(ctx.counters),
            "line_count": len(text.splitlines()),
            "char_count": len(text),
        }

    @classmethod
    def capture_device_outputs(
        cls,
        db: Session,
        *,
        device: Device,
        commands: Iterable[str],
    ) -> Dict[str, Any]:
        policy = cls.get_policy(db)
        if not policy.get("preview_enabled"):
            raise PermissionError("Preview edition is not enabled.")
        if not policy.get("capture_enabled"):
            raise PermissionError("Preview capture is disabled.")
        if not policy.get("allow_device_capture"):
            raise PermissionError("Device capture is disabled by preview policy.")

        allowed_commands = cls.ensure_commands_allowed(commands, db=db, policy=policy)
        if not device.ssh_username or not device.ssh_password:
            raise ValueError("Device is missing SSH credentials.")

        conn = DeviceConnection(
            DeviceInfo(
                host=device.ip_address,
                username=device.ssh_username,
                password=device.ssh_password,
                secret=device.enable_password,
                port=device.ssh_port or 22,
                device_type=device.device_type or "cisco_ios",
            )
        )
        if not conn.connect():
            raise ConnectionError(conn.last_error or "Failed to connect to device.")

        entries: List[Dict[str, Any]] = []
        failures: List[Dict[str, str]] = []
        try:
            for command in allowed_commands:
                try:
                    output = str(conn.send_command(command, read_timeout=45) or "")
                    entries.append(cls.sanitize_output(command=command, raw_output=output, device=device))
                except Exception as exc:
                    failures.append({"command": command, "error": str(exc)})
        finally:
            conn.disconnect()

        return {
            "device": cls.sanitized_device_context(device),
            "entries": entries,
            "failures": failures,
            "captured_commands": [item["command"] for item in entries],
        }

    @staticmethod
    def sanitized_device_context(device: Device | None) -> Dict[str, Any]:
        if device is None:
            return {}
        return {
            "id": int(device.id),
            "device_type": str(device.device_type or ""),
            "model": str(device.model or ""),
            "os_version": str(device.os_version or ""),
            "role": str(device.role or ""),
            "site_id": int(device.site_id) if getattr(device, "site_id", None) is not None else None,
        }

    @staticmethod
    def normalize_external_device_context(device_context: Dict[str, Any] | None) -> Dict[str, Any]:
        raw = dict(device_context or {})
        out = {
            "device_type": str(raw.get("device_type") or "").strip(),
            "model": str(raw.get("model") or "").strip(),
            "os_version": str(raw.get("os_version") or "").strip(),
            "role": str(raw.get("role") or "").strip(),
            "site_id": raw.get("site_id"),
        }
        if out["site_id"] in {"", None}:
            out["site_id"] = None
        return out

    @classmethod
    def _build_contribution_payload(
        cls,
        *,
        device: Device | None,
        device_context_override: Dict[str, Any] | None,
        source: str,
        entries: List[Dict[str, Any]],
        notes: str,
        consent_confirmed: bool,
        submitter_role: str,
        collector_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        contribution_id = f"preview-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        summary = {
            "ip": 0,
            "mac": 0,
            "email": 0,
            "serial": 0,
            "host": 0,
            "url": 0,
            "secret_lines": 0,
            "certificate_blocks": 0,
        }
        device_context = cls.sanitized_device_context(device)
        if not device_context:
            device_context = cls.normalize_external_device_context(device_context_override)

        sanitized_entries: List[Dict[str, Any]] = []
        for raw in entries:
            sanitized = cls.sanitize_output(
                command=str(raw.get("command") or "").strip(),
                raw_output=str(raw.get("raw_output") or raw.get("sanitized_output") or ""),
                device=device,
                host_candidates=[str((device_context_override or {}).get("hostname") or "").strip()],
            )
            for key, value in dict(sanitized.get("redaction_summary") or {}).items():
                summary[key] = summary.get(key, 0) + int(value or 0)
            sanitized_entries.append(sanitized)

        return {
            "id": contribution_id,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "edition": "preview",
            "source": str(source or "manual"),
            "consent_confirmed": bool(consent_confirmed),
            "notes": str(notes or "").strip(),
            "device": device_context,
            "collector_context": dict(collector_context or {}),
            "submitter_role": str(submitter_role or "").strip() or "viewer",
            "entry_count": len(sanitized_entries),
            "redaction_summary": summary,
            "entries": sanitized_entries,
        }

    @classmethod
    def _write_payload_to_storage(cls, db: Session, payload: Dict[str, Any]) -> Path:
        storage_dir = cls._storage_dir(db)
        storage_dir.mkdir(parents=True, exist_ok=True)
        day_dir = storage_dir / datetime.now(timezone.utc).strftime("%Y%m%d")
        day_dir.mkdir(parents=True, exist_ok=True)
        out_path = day_dir / f"{str(payload.get('id') or uuid4().hex)}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path

    @classmethod
    def authenticate_intake_registration(
        cls,
        db: Session,
        *,
        collector_id: str | None,
        token: str | None,
        policy: Dict[str, Any] | None = None,
    ) -> PreviewCollectorRegistration | None:
        resolved_policy = policy or cls.get_policy(db)
        if not resolved_policy.get("accept_remote_uploads"):
            return None
        clean_collector_id = str(collector_id or "").strip()
        clean_token = str(token or "").strip()
        if not clean_collector_id or not clean_token:
            return None
        registration = (
            db.query(PreviewCollectorRegistration)
            .filter(
                PreviewCollectorRegistration.collector_id == clean_collector_id,
                PreviewCollectorRegistration.is_active.is_(True),
            )
            .first()
        )
        if registration is None:
            return None
        provided_hash = cls._hash_registration_token(clean_token)
        if not secrets.compare_digest(str(registration.token_hash or ""), provided_hash):
            return None
        registration.last_used_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(registration)
        return registration

    @classmethod
    def set_upload_participation(
        cls,
        db: Session,
        *,
        user: User | None,
        enabled: bool,
        source: str = "wizard",
    ) -> Dict[str, Any]:
        policy = cls.get_policy(db)
        if not policy.get("preview_enabled"):
            raise PermissionError("Preview edition is not enabled.")
        if not policy.get("upload_feature_available") and enabled:
            raise PermissionError("Preview contribution upload is disabled by product policy.")
        if policy.get("upload_decision_recorded") and policy.get("upload_locked"):
            raise PermissionError(
                "Preview contribution policy is locked for this installation. Reset or reinstall to change it."
            )
        if (
            policy.get("deployment_role") != "intake_server"
            and str(source or "").strip() != "first_run_wizard"
        ):
            raise PermissionError(
                "Preview contribution policy can only be recorded during first-run setup."
            )

        enrollment_result: Dict[str, Any] | None = None
        if enabled:
            enrollment_result = cls.ensure_remote_upload_registration(
                db,
                user=user,
                source=source,
                policy=policy,
            )

        state = "enabled" if bool(enabled) else "disabled"
        recorded_at = datetime.now(timezone.utc).isoformat()
        actor = str(getattr(user, "username", "") or "anonymous").strip() or "anonymous"
        actor_label = actor if not source else f"{actor}:{str(source).strip() or 'manual'}"
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_PARTICIPATION_KEY,
            value=state,
            description="Preview contribution participation state",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_PARTICIPATION_RECORDED_AT_KEY,
            value=recorded_at,
            description="When preview contribution participation was last recorded",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_PARTICIPATION_ACTOR_KEY,
            value=actor_label,
            description="Who last recorded preview contribution participation",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_LOCKED_KEY,
            value="true",
            description="Whether preview contribution policy is locked for this installation",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_CHANGE_REQUIRES_RESET_KEY,
            value="true",
            description="Whether changing preview contribution policy requires reset or reinstall",
        )
        cls._upsert_setting(
            db,
            key=cls.SETTING_UPLOAD_SCOPE_KEY,
            value=cls.DEFAULT_CONTRIBUTION_SCOPE,
            description="Allowed preview contribution scope",
        )
        db.commit()
        return {
            "state": state,
            "recorded_at": recorded_at,
            "recorded_by": actor_label,
            "enrollment": enrollment_result or {},
            "policy": cls.get_policy(db),
        }

    @classmethod
    def ensure_remote_upload_registration(
        cls,
        db: Session,
        *,
        user: User | None = None,
        source: str = "auto_enroll",
        policy: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        resolved_policy = policy or cls.get_policy(db)
        if resolved_policy.get("deployment_role") != "collector_installed":
            return {"status": "not_required"}
        if resolved_policy.get("upload_target_mode") not in {"remote_only", "dual_write"}:
            return {"status": "not_required"}
        if not resolved_policy.get("self_registration_enabled"):
            return {"status": "disabled"}

        remote_upload_url = cls._normalize_remote_upload_url(resolved_policy.get("remote_upload_url"))
        if not remote_upload_url:
            message = "Remote preview intake URL is not configured."
            cls._mark_remote_upload_registration_error(db, error=message, source=source)
            raise cls.RemoteUploadError(message)

        collector_id = str(resolved_policy.get("remote_upload_client_id") or "").strip()
        token = str(resolved_policy.get("remote_upload_token") or "").strip()
        if collector_id and token:
            return {
                "status": "already_registered",
                "collector_id": collector_id,
            }

        enrollment_url = cls._derive_remote_enrollment_url(remote_upload_url)
        if not enrollment_url:
            message = "Remote preview intake enrollment endpoint could not be derived."
            cls._mark_remote_upload_registration_error(db, error=message, source=source)
            raise cls.RemoteUploadError(message)

        installation_id = cls.get_or_create_installation_id(db)
        requested_label = cls._default_self_registration_label(installation_id)
        username = str(getattr(user, "username", "") or "").strip()
        payload = {
            "installation_id": installation_id,
            "requested_label": requested_label,
            "source": str(source or "").strip() or "auto_enroll",
            "consent_confirmed": True,
            "metadata": {
                "deployment_role": str(resolved_policy.get("deployment_role") or ""),
                "upload_target_mode": str(resolved_policy.get("upload_target_mode") or ""),
                "actor": username or "anonymous",
            },
        }
        timeout_raw = str(resolved_policy.get("remote_upload_timeout_seconds") or "10").strip()
        try:
            timeout = max(3.0, float(timeout_raw))
        except Exception:
            timeout = 10.0

        try:
            response = requests.post(
                enrollment_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            message = f"Preview contribution auto-registration failed: {exc}"
            cls._mark_remote_upload_registration_error(db, error=message, source=source)
            raise cls.RemoteUploadError(message) from exc

        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        if not isinstance(data, dict):
            message = "Preview contribution auto-registration returned an invalid response."
            cls._mark_remote_upload_registration_error(db, error=message, source=source)
            raise cls.RemoteUploadError(message)

        issued_collector_id = str(data.get("collector_id") or "").strip()
        issued_token = str(data.get("intake_token") or "").strip()
        returned_upload_url = cls._normalize_remote_upload_url(data.get("upload_url") or remote_upload_url)
        if not issued_collector_id or not issued_token:
            message = "Preview contribution auto-registration did not return collector credentials."
            cls._mark_remote_upload_registration_error(db, error=message, source=source)
            raise cls.RemoteUploadError(message)

        if returned_upload_url and returned_upload_url != remote_upload_url:
            cls._upsert_setting(
                db,
                key=cls.SETTING_REMOTE_UPLOAD_URL_KEY,
                value=returned_upload_url,
                description="Preview remote upload endpoint",
            )
        cls._store_remote_upload_registration(
            db,
            collector_id=issued_collector_id,
            intake_token=issued_token,
            source=source,
        )
        return {
            "status": "registered",
            "collector_id": issued_collector_id,
            "upload_url": returned_upload_url or remote_upload_url,
        }

    @classmethod
    def _forward_payload_to_remote(cls, payload: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
        url = cls._normalize_remote_upload_url(policy.get("remote_upload_url"))
        collector_id = str(policy.get("remote_upload_client_id") or "").strip()
        token = str(policy.get("remote_upload_token") or "").strip()
        if not url or not collector_id or not token:
            raise cls.RemoteUploadError("Remote preview intake is not configured.")
        timeout_raw = str(policy.get("remote_upload_timeout_seconds") or "10").strip()
        try:
            timeout = max(3.0, float(timeout_raw))
        except Exception:
            timeout = 10.0

        request_body = {
            "source": str(payload.get("source") or "collector_forward"),
            "consent_confirmed": bool(payload.get("consent_confirmed")),
            "notes": str(payload.get("notes") or ""),
            "device_context": dict(payload.get("device") or {}),
            "collector_context": dict(payload.get("collector_context") or {}),
            "entries": [
                {
                    "command": str(entry.get("command") or ""),
                    "sanitized_output": str(entry.get("sanitized_output") or ""),
                }
                for entry in list(payload.get("entries") or [])
            ],
        }
        headers = {
            "X-Preview-Collector-Id": collector_id,
            "X-Preview-Intake-Token": token,
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=request_body, headers=headers, timeout=timeout)
            response.raise_for_status()
        except Exception as exc:
            raise cls.RemoteUploadError(f"Remote preview upload failed: {exc}") from exc
        try:
            data = response.json()
        except Exception:
            data = {}
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
            data = data["data"]
        return data if isinstance(data, dict) else {}

    @classmethod
    def persist_contribution(
        cls,
        db: Session,
        *,
        user: User | None,
        device: Device | None,
        source: str,
        entries: List[Dict[str, Any]],
        notes: str = "",
        consent_confirmed: bool,
        device_context_override: Dict[str, Any] | None = None,
        collector_context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        policy = cls.get_policy(db)
        if not policy.get("preview_enabled"):
            raise PermissionError("Preview edition is not enabled.")
        if not policy.get("upload_feature_available"):
            raise PermissionError("Preview contribution upload is disabled.")
        if policy.get("upload_opt_in_required") and not policy.get("upload_opt_in_enabled"):
            raise PermissionError("Preview contribution upload is not active. Enable optional data sharing first.")
        if not policy.get("upload_enabled"):
            raise PermissionError("Preview contribution upload is disabled.")
        if policy.get("require_consent") and not consent_confirmed:
            raise ValueError("Consent confirmation is required.")

        for raw in entries:
            command = str(raw.get("command") or "").strip()
            if not cls.is_command_allowed(command, db=db, policy=policy):
                raise ValueError(f"Command blocked by preview policy: {command}")
        submitter_role = str(getattr(user, "role", "") or "collector").strip() or "collector"
        payload = cls._build_contribution_payload(
            device=device,
            device_context_override=device_context_override,
            source=source,
            entries=entries,
            notes=notes,
            consent_confirmed=consent_confirmed,
            submitter_role=submitter_role,
            collector_context=collector_context,
        )

        mode = str(policy.get("upload_target_mode") or "local_only")
        local_saved = False
        remote_forwarded = False
        remote_result: Dict[str, Any] = {}

        if mode in {"local_only", "dual_write"}:
            cls._write_payload_to_storage(db, payload)
            local_saved = True

        if mode in {"remote_only", "dual_write"}:
            enrollment_result = cls.ensure_remote_upload_registration(
                db,
                user=user,
                source="persist_contribution",
                policy=policy,
            )
            forward_policy = dict(policy)
            remote_values = cls._read_settings(
                db,
                [
                    cls.SETTING_REMOTE_UPLOAD_URL_KEY,
                    cls.SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY,
                    cls.SETTING_REMOTE_UPLOAD_TOKEN_KEY,
                ],
            )
            forward_policy["remote_upload_url"] = cls._normalize_remote_upload_url(
                cls._resolve_setting(remote_values, cls.SETTING_REMOTE_UPLOAD_URL_KEY, "")
            )
            forward_policy["remote_upload_client_id"] = cls._resolve_setting(
                remote_values,
                cls.SETTING_REMOTE_UPLOAD_CLIENT_ID_KEY,
                "",
            )
            forward_policy["remote_upload_token"] = cls._resolve_setting(
                remote_values,
                cls.SETTING_REMOTE_UPLOAD_TOKEN_KEY,
                "",
            )
            remote_result = cls._forward_payload_to_remote(payload, forward_policy)
            if enrollment_result:
                remote_result.setdefault("registration", enrollment_result)
            remote_forwarded = True

        return {
            "id": str(payload.get("id") or ""),
            "saved": local_saved or remote_forwarded,
            "entry_count": int(payload.get("entry_count") or 0),
            "redaction_summary": payload.get("redaction_summary") or {},
            "storage_bucket": cls._storage_dir(db).name,
            "delivery": {
                "mode": mode,
                "local_saved": local_saved,
                "remote_forwarded": remote_forwarded,
                "remote_destination": str(policy.get("remote_upload_destination") or ""),
                "remote_result": remote_result,
            },
        }

    @classmethod
    def list_recent_contributions(cls, db: Session, limit: int = 20) -> List[Dict[str, Any]]:
        storage_dir = cls._storage_dir(db)
        if not storage_dir.exists():
            return []
        files = sorted(storage_dir.rglob("preview-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        out: List[Dict[str, Any]] = []
        for path in files[: max(1, min(int(limit), 100))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            out.append(
                {
                    "id": str(payload.get("id") or ""),
                    "submitted_at": str(payload.get("submitted_at") or ""),
                    "source": str(payload.get("source") or ""),
                    "entry_count": int(payload.get("entry_count") or 0),
                    "device_type": str((payload.get("device") or {}).get("device_type") or ""),
                    "model": str((payload.get("device") or {}).get("model") or ""),
                    "redaction_summary": payload.get("redaction_summary") or {},
                }
            )
        return out

    @classmethod
    def get_contribution_record(cls, db: Session, contribution_id: str) -> Dict[str, Any] | None:
        clean_id = str(contribution_id or "").strip()
        if not clean_id:
            return None
        storage_dir = cls._storage_dir(db)
        if not storage_dir.exists():
            return None
        candidate = None
        for path in storage_dir.rglob(f"{clean_id}.json"):
            candidate = path
            break
        if candidate is None:
            return None
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return {
            "id": str(payload.get("id") or ""),
            "submitted_at": str(payload.get("submitted_at") or ""),
            "source": str(payload.get("source") or ""),
            "notes": str(payload.get("notes") or ""),
            "entry_count": int(payload.get("entry_count") or 0),
            "submitter_role": str(payload.get("submitter_role") or ""),
            "device": payload.get("device") or {},
            "collector_context": payload.get("collector_context") or {},
            "redaction_summary": payload.get("redaction_summary") or {},
            "entries": payload.get("entries") or [],
        }

    @classmethod
    def is_mutation_blocked(cls, db: Session, method: str, path: str) -> bool:
        if not cls.is_preview_enabled(db):
            return False
        method_name = str(method or "").upper()
        if method_name in {"GET", "HEAD", "OPTIONS"}:
            return False
        normalized = str(path or "").rstrip("/")
        if normalized.startswith("/api/v1/preview"):
            return False
        if normalized in cls.BLOCKED_MUTATION_EXACT:
            return True
        if any(normalized.startswith(prefix) for prefix in cls.BLOCKED_MUTATION_PREFIXES):
            return True
        if any(fragment in normalized for fragment in cls.BLOCKED_MUTATION_CONTAINS):
            return True
        if any(normalized.startswith(prefix) for prefix in cls.ALLOWED_MUTATION_PREFIXES):
            return False
        return True
