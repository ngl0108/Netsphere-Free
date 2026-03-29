from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import threading
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.ha_lease import HaLease
from app.models.settings import SystemSetting


@dataclass
class HaState:
    enabled: bool
    role: str  # active | standby | disabled
    node_id: str
    lease_key: str
    leader_id: Optional[str]
    lease_expires_at: Optional[datetime]
    updated_at: datetime


class HaService:
    @staticmethod
    def _env_alias(*keys: str) -> str | None:
        for key in keys:
            value = os.getenv(str(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _get_str(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(HaService._get_str(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = HaService._get_str(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def node_id(db: Optional[Session] = None) -> str:
        env = (
            HaService._env_alias("NETSPHERE_NODE_ID", "NETMANAGER_NODE_ID")
            or os.getenv("HOSTNAME")
            or os.getenv("COMPUTERNAME")
        )
        if env:
            return str(env)
        if db is not None:
            v = HaService._get_str(db, "ha_node_id", "").strip()
            if v:
                return v
        return "netmanager-node"

    @staticmethod
    def enabled(db: Session) -> bool:
        env = HaService._env_alias("NETSPHERE_HA_ENABLED", "NETMANAGER_HA_ENABLED")
        if env is not None:
            return str(env).strip().lower() in {"1", "true", "yes", "y", "on"}
        return HaService._get_bool(db, "ha_enabled", False)

    @staticmethod
    def standby_readonly(db: Session) -> bool:
        return HaService._get_bool(db, "ha_standby_readonly", True)

    @staticmethod
    def lease_key(db: Session) -> str:
        v = HaService._get_str(db, "ha_lease_key", "netsphere-controller").strip()
        return v or "netsphere-controller"

    @staticmethod
    def lease_ttl_seconds(db: Session) -> int:
        v = HaService._get_int(db, "ha_lease_ttl_seconds", 15)
        if v < 5:
            v = 5
        if v > 120:
            v = 120
        return v

    @staticmethod
    def leader_url(db: Session) -> Optional[str]:
        v = HaService._get_str(db, "ha_leader_url", "").strip()
        return v or None

    @staticmethod
    def renew_interval_seconds(db: Session) -> int:
        v = HaService._get_int(db, "ha_lease_renew_interval_seconds", 5)
        if v < 1:
            v = 1
        if v > 60:
            v = 60
        return v

    @staticmethod
    def try_acquire_or_renew(db: Session, *, key: str, node_id: str, ttl_seconds: int):
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=float(ttl_seconds))

        q = db.query(HaLease).filter(HaLease.key == str(key))
        try:
            dialect = db.get_bind().dialect.name
        except Exception:
            dialect = ""
        if dialect == "postgresql":
            q = q.with_for_update()
        lease = q.first()

        if not lease:
            lease = HaLease(
                key=str(key),
                owner_id=str(node_id),
                acquired_at=now,
                last_renewed_at=now,
                expires_at=expires_at,
            )
            db.add(lease)
            db.flush()
            return True, str(node_id), expires_at

        current_owner = str(getattr(lease, "owner_id", "") or "")
        cur_expires = getattr(lease, "expires_at", None)
        try:
            if cur_expires and getattr(cur_expires, "tzinfo", None) is None:
                cur_expires = cur_expires.replace(tzinfo=timezone.utc)
        except Exception:
            cur_expires = None

        if current_owner == str(node_id):
            lease.last_renewed_at = now
            lease.expires_at = expires_at
            db.add(lease)
            db.flush()
            return True, current_owner, expires_at

        if cur_expires and now > cur_expires:
            lease.owner_id = str(node_id)
            lease.acquired_at = now
            lease.last_renewed_at = now
            lease.expires_at = expires_at
            db.add(lease)
            db.flush()
            return True, str(node_id), expires_at

        return False, current_owner or None, cur_expires

    @staticmethod
    def current_role(db: Session) -> str:
        if not HaService.enabled(db):
            return "disabled"
        node_id = HaService.node_id(db)
        lease_key = HaService.lease_key(db)
        now = datetime.now(timezone.utc)

        lease = db.query(HaLease).filter(HaLease.key == str(lease_key)).first()
        if not lease:
            return "standby"
        leader_id = str(getattr(lease, "owner_id", "") or "")
        expires_at = getattr(lease, "expires_at", None)
        try:
            if expires_at and getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            expires_at = None
        if expires_at and now > expires_at:
            return "standby"
        if leader_id and leader_id == str(node_id):
            return "active"
        return "standby"

    @staticmethod
    def is_active(db: Session) -> bool:
        return HaService.current_role(db) == "active"


class HaManager:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._state = HaState(
            enabled=False,
            role="disabled",
            node_id=HaService.node_id(),
            lease_key="netsphere-controller",
            leader_id=None,
            lease_expires_at=None,
            updated_at=datetime.now(timezone.utc),
        )

    def get_state(self) -> HaState:
        with self._lock:
            return self._state

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        t = threading.Thread(target=self._run, name="ha-manager", daemon=True)
        self._thread = t
        t.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _set_state(
        self,
        *,
        enabled: bool,
        role: str,
        node_id: str,
        lease_key: str,
        leader_id: Optional[str],
        lease_expires_at: Optional[datetime],
    ):
        with self._lock:
            self._state = HaState(
                enabled=bool(enabled),
                role=str(role),
                node_id=str(node_id),
                lease_key=str(lease_key),
                leader_id=leader_id,
                lease_expires_at=lease_expires_at,
                updated_at=datetime.now(timezone.utc),
            )

    def _run(self):
        while not self._stop.is_set():
            db = SessionLocal()
            try:
                enabled = HaService.enabled(db)
                node_id = HaService.node_id(db)
                lease_key = HaService.lease_key(db)
                ttl = HaService.lease_ttl_seconds(db)
                renew = HaService.renew_interval_seconds(db)

                if not enabled:
                    self._set_state(
                        enabled=False,
                        role="disabled",
                        node_id=node_id,
                        lease_key=lease_key,
                        leader_id=None,
                        lease_expires_at=None,
                    )
                    time.sleep(2.0)
                    continue

                with db.begin():
                    is_leader, leader_id, lease_expires_at = HaService.try_acquire_or_renew(
                        db,
                        key=lease_key,
                        node_id=node_id,
                        ttl_seconds=ttl,
                    )

                self._set_state(
                    enabled=True,
                    role="active" if is_leader else "standby",
                    node_id=node_id,
                    lease_key=lease_key,
                    leader_id=leader_id,
                    lease_expires_at=lease_expires_at,
                )
                time.sleep(float(renew))
            except Exception:
                self._set_state(
                    enabled=True,
                    role="standby",
                    node_id=HaService.node_id(),
                    lease_key="netsphere-controller",
                    leader_id=None,
                    lease_expires_at=None,
                )
                time.sleep(2.0)
            finally:
                db.close()
