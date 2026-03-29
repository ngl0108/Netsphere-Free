from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from app.db.session import SessionLocal
from app.models.settings import SystemSetting
from app.services.discovery_hint_sync_service import DiscoveryHintSyncService


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _acquire_lock(db, key: str, ttl_seconds: int = 60) -> bool:
    now = datetime.utcnow()
    lock_until = now + timedelta(seconds=max(30, int(ttl_seconds)))
    row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
    if row and getattr(row, "value", None):
        current = _parse_iso(getattr(row, "value", None))
        if current and current > now:
            return False
    if row is None:
        row = SystemSetting(key=str(key), value=lock_until.isoformat(), description=key, category="discovery_hint")
    else:
        row.value = lock_until.isoformat()
        row.description = row.description or key
        row.category = row.category or "discovery_hint"
    db.add(row)
    db.commit()
    return True


class DiscoveryHintSyncScheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="discovery_hint_sync_scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            try:
                thread.join(timeout=2.0)
            except Exception:
                pass

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick_once()
            except Exception:
                pass
            time.sleep(1.0)

    def _tick_once(self) -> None:
        if not DiscoveryHintSyncService.is_enabled():
            return

        db = SessionLocal()
        try:
            if not _acquire_lock(db, "discovery_hint_sync_scheduler_tick_lock", ttl_seconds=45):
                return

            now = datetime.utcnow()

            pull_due = self._is_pull_due(db, now)
            push_due = self._is_push_due(db, now)

            if pull_due:
                DiscoveryHintSyncService._set_setting(
                    db,
                    key=DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY,
                    value=now.isoformat(),
                    description="When discovery hint remote rule pull was last attempted by the scheduler",
                )
                db.commit()
                DiscoveryHintSyncService.pull_rule_snapshot(db)

            if push_due:
                DiscoveryHintSyncService._set_setting(
                    db,
                    key=DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY,
                    value=now.isoformat(),
                    description="When discovery hint telemetry push was last attempted by the scheduler",
                )
                db.commit()
                DiscoveryHintSyncService.push_recent_telemetry(db)
        finally:
            db.close()

    def _is_pull_due(self, db, now: datetime) -> bool:
        last_attempt = _parse_iso(
            DiscoveryHintSyncService._get_setting(
                db,
                DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY,
                "",
            )
        )
        if last_attempt is None:
            return True
        return now - last_attempt >= timedelta(seconds=DiscoveryHintSyncService.pull_interval_seconds())

    def _is_push_due(self, db, now: datetime) -> bool:
        last_attempt = _parse_iso(
            DiscoveryHintSyncService._get_setting(
                db,
                DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY,
                "",
            )
        )
        if last_attempt is None:
            return True
        return now - last_attempt >= timedelta(seconds=DiscoveryHintSyncService.push_interval_seconds())
