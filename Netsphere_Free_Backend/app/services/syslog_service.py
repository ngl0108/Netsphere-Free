import asyncio
import logging
import os
import re
import time
from datetime import datetime

from app.db.session import SessionLocal
from app.models.device import Device, EventLog, Issue, Link

IGNORED_PATTERNS = [
    "IP_SNMP-4-NOTRAPIP",
    "SYS-6-TTY_EXPIRE_TIMER",
]

logger = logging.getLogger(__name__)


def process_syslog_message(source_ip: str, raw_log: str) -> None:
    db = SessionLocal()
    try:
        if any(pattern in raw_log for pattern in IGNORED_PATTERNS):
            return

        device = db.query(Device).filter(Device.ip_address == source_ip).first()
        if not device:
            return

        match = re.search(r"%([A-Z0-9_]+)-([0-7])-([A-Z0-9_]+):\s*(.*)", raw_log)

        event_id = "SYSLOG"
        severity_code = 6
        message = raw_log

        if match:
            facility = match.group(1)
            severity_code = int(match.group(2))
            mnemonic = match.group(3)
            message = match.group(4).strip()
            event_id = f"%{facility}-{severity_code}-{mnemonic}"

        db_severity = "info"
        issue_title = event_id

        if "FAN-3-FAIL" in event_id or ("FAN" in message.upper() and "FAIL" in message.upper()):
            db_severity = "critical"
            issue_title = f"Fan Failure: {device.name}"
        elif "ENV-3-TEMP" in event_id or ("TEMPERATURE" in message.upper() and "CRITICAL" in message.upper()):
            db_severity = "critical"
            issue_title = f"Temperature Critical: {device.name}"
        elif "POWER" in event_id and "FAIL" in event_id:
            db_severity = "critical"
            issue_title = f"Power Supply Failure: {device.name}"
        elif "OSPF-5-ADJCHANGE" in event_id:
            if "DOWN" in message.upper():
                db_severity = "warning"
                issue_title = f"OSPF Neighbor Down: {device.name}"
        elif "BGP-5-ADJCHANGE" in event_id or "BGP-5-ADJCHANGE" in raw_log:
            if "DOWN" in message.upper():
                db_severity = "warning"
                issue_title = f"BGP Neighbor Down: {device.name}"
        elif "CONFIG_I" in event_id or "SYS-5-CONFIG_I" in event_id:
            db_severity = "warning"
            issue_title = f"Configuration Changed: {device.name}"
        elif severity_code <= 2:
            db_severity = "critical"
        elif severity_code <= 4:
            db_severity = "warning"

        if "UPDOWN" in event_id:
            if_match = re.search(r"Interface\s+([A-Za-z0-9\/\-\.]+)", message)
            state_match = re.search(r"changed state to\s+(up|down)", message, re.IGNORECASE)
            if if_match and state_match:
                if_name = if_match.group(1).strip()
                new_state = state_match.group(1).lower()

                from app.models.device import Interface

                target_if = (
                    db.query(Interface)
                    .filter(Interface.device_id == device.id, Interface.name == if_name)
                    .first()
                )
                if target_if:
                    target_if.status = new_state
                    now = datetime.now()
                    db.commit()

                    def _n(x: str) -> str:
                        return str(x or "").strip().lower().replace(" ", "")

                    normalized_if = _n(if_name)
                    touched: list[int] = []
                    links = db.query(Link).filter(
                        (Link.source_device_id == device.id) | (Link.target_device_id == device.id)
                    ).all()
                    for l in links:
                        if l.source_device_id == device.id and _n(l.source_interface_name) == normalized_if:
                            l.status = "down" if new_state == "down" else "up"
                            l.last_seen = now
                            touched.append(l.id)
                        elif l.target_device_id == device.id and _n(l.target_interface_name) == normalized_if:
                            l.status = "down" if new_state == "down" else "up"
                            l.last_seen = now
                            touched.append(l.id)

                    if touched:
                        db.commit()
                        try:
                            from app.services.realtime_event_bus import realtime_event_bus

                            realtime_event_bus.publish(
                                "link_update",
                                {
                                    "device_id": device.id,
                                    "device_ip": device.ip_address,
                                    "interface": if_name,
                                    "state": new_state,
                                    "link_ids": touched,
                                    "ts": now.isoformat(),
                                },
                            )
                        except Exception:
                            pass

        db.add(
            EventLog(
                device_id=device.id,
                severity=db_severity,
                event_id=event_id,
                message=message,
                source="Syslog",
                timestamp=datetime.now(),
            )
        )
        try:
            db.commit()
        except Exception:
            db.rollback()

        if db_severity in {"critical", "warning"}:
            exists = (
                db.query(Issue)
                .filter(
                    Issue.device_id == device.id,
                    Issue.title == issue_title,
                    Issue.status == "active",
                )
                .first()
            )
            if not exists:
                db.add(
                    Issue(
                        device_id=device.id,
                        title=issue_title,
                        description=message,
                        severity=db_severity,
                        status="active",
                    )
                )
                db.commit()
    finally:
        db.close()


class SyslogProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        super().__init__()
        self.queue_size = int(os.getenv("SYSLOG_QUEUE_SIZE", "20000"))
        self.worker_count = int(os.getenv("SYSLOG_WORKERS", "4"))
        self.queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=self.queue_size)
        self._workers: list[asyncio.Task] = []
        self._dropped = 0
        self._last_drop_log = 0.0
        self.drop_log_interval_sec = float(os.getenv("SYSLOG_DROP_LOG_INTERVAL_SEC", "5.0"))

    def connection_made(self, transport):
        self.transport = transport
        if not self._workers:
            for _ in range(max(1, self.worker_count)):
                self._workers.append(asyncio.create_task(self._worker_loop()))

    def connection_lost(self, exc):
        for t in self._workers:
            t.cancel()
        self._workers.clear()

    def datagram_received(self, data, addr):
        try:
            raw_log = data.decode("utf-8", errors="ignore").strip()
            source_ip = addr[0]
            try:
                self.queue.put_nowait((source_ip, raw_log))
            except asyncio.QueueFull:
                if not self._enqueue_to_celery(source_ip, raw_log):
                    self._dropped += 1
                    now = time.monotonic()
                    if now - self._last_drop_log >= self.drop_log_interval_sec:
                        self._last_drop_log = now
                        logger.warning("Syslog queue full; dropped=%s", self._dropped)
        except Exception:
            logger.exception("Error receiving syslog")

    async def process_log(self, source_ip: str, raw_log: str) -> None:
        if not self._enqueue_to_celery(source_ip, raw_log):
            await asyncio.to_thread(process_syslog_message, source_ip, raw_log)

    async def _worker_loop(self) -> None:
        while True:
            source_ip, raw_log = await self.queue.get()
            try:
                if not self._enqueue_to_celery(source_ip, raw_log):
                    await asyncio.to_thread(process_syslog_message, source_ip, raw_log)
            except Exception:
                logger.exception("Syslog worker error")
            finally:
                self.queue.task_done()

    def _enqueue_to_celery(self, source_ip: str, raw_log: str) -> bool:
        try:
            from app.tasks.syslog_ingest import ingest_syslog

            if hasattr(ingest_syslog, "apply_async"):
                ingest_syslog.apply_async(
                    args=[source_ip, raw_log],
                    queue=os.getenv("SYSLOG_CELERY_QUEUE", "syslog"),
                )
                return True
            return False
        except Exception:
            return False
