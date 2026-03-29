from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Optional

from app.db.session import SessionLocal
from app.services.ha_service import HaService


def _env_alias(*keys: str) -> str | None:
    for key in keys:
        value = os.getenv(str(key))
        if value is not None:
            return value
    return None


class BeatGuard:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.stop = False

    def _handle_term(self, *_):
        self.stop = True
        self._stop_proc()

    def _start_proc(self):
        if self.proc and self.proc.poll() is None:
            return
        cmd = ["celery", "-A", "celery_app", "beat", "--loglevel", os.getenv("CELERY_LOGLEVEL", "info")]
        schedule_file = str(os.getenv("CELERY_BEAT_SCHEDULE_FILE", "/tmp/celerybeat-schedule")).strip()
        if schedule_file:
            cmd.extend(["--schedule", schedule_file])
        # Drop privileges for beat subprocess by default when container starts as root.
        try:
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                uid = str(os.getenv("CELERY_RUN_UID", "65534")).strip() or "65534"
                gid = str(os.getenv("CELERY_RUN_GID", "65534")).strip() or "65534"
                cmd.extend(["--uid", uid, "--gid", gid])
        except Exception:
            pass
        self.proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)

    def _stop_proc(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            self.proc.terminate()
        except Exception:
            pass
        for _ in range(20):
            if self.proc.poll() is not None:
                return
            time.sleep(0.1)
        try:
            self.proc.kill()
        except Exception:
            pass

    def _should_run(self) -> bool:
        env_flag = _env_alias("NETSPHERE_HA_ENABLED", "NETMANAGER_HA_ENABLED")
        env_enabled = None
        if env_flag is not None:
            env_enabled = str(env_flag).strip().lower() in {"1", "true", "yes", "y", "on"}

        db = SessionLocal()
        try:
            if not HaService.enabled(db):
                return True

            lease_key = HaService.lease_key(db)
            node_id = HaService.node_id(db)
            ttl = HaService.lease_ttl_seconds(db)
            with db.begin():
                is_leader, leader_id, lease_expires_at = HaService.try_acquire_or_renew(
                    db,
                    key=lease_key,
                    node_id=node_id,
                    ttl_seconds=ttl,
                )
            return bool(is_leader)
        except Exception:
            if env_enabled is True:
                return False
            return True
        finally:
            db.close()

    def run(self):
        signal.signal(signal.SIGTERM, self._handle_term)
        signal.signal(signal.SIGINT, self._handle_term)

        interval = float(_env_alias("NETSPHERE_HA_BEAT_GUARD_INTERVAL_SEC", "NETMANAGER_HA_BEAT_GUARD_INTERVAL_SEC") or "3")
        if interval < 1:
            interval = 1.0
        if interval > 30:
            interval = 30.0

        while not self.stop:
            try:
                if self._should_run():
                    self._start_proc()
                else:
                    self._stop_proc()
            except Exception:
                self._stop_proc()
            time.sleep(interval)


def main():
    BeatGuard().run()


if __name__ == "__main__":
    main()
