from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Set

try:
    import redis
except Exception:  # pragma: no cover
    redis = None


@dataclass(frozen=True)
class RealtimeEvent:
    event: str
    data: Dict[str, Any]


class RealtimeEventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: Set[queue.Queue[RealtimeEvent]] = set()
        self._origin = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis_channel = os.getenv("REALTIME_EVENTS_CHANNEL", "realtime_events")
        self._throttle_sec = float(os.getenv("REALTIME_EVENT_THROTTLE_SEC", "0.5"))
        self._last_sent: Dict[str, float] = {}
        self._throttle_events = {"metrics_update", "device_status", "link_update"}
        self._redis_client = None
        self._redis_thread = None
        self._redis_stop = threading.Event()

    def subscribe(self) -> queue.Queue[RealtimeEvent]:
        q: queue.Queue[RealtimeEvent] = queue.Queue(maxsize=500)
        with self._lock:
            self._subscribers.add(q)
        self._ensure_redis_listener()
        return q

    def unsubscribe(self, q: queue.Queue[RealtimeEvent]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: str, data: Dict[str, Any]) -> None:
        if self._should_throttle(event, data):
            return
        self._publish_local(event, data)
        self._publish_redis(event, data)

    def _should_throttle(self, event: str, data: Dict[str, Any]) -> bool:
        if self._throttle_sec <= 0:
            return False
        if event not in self._throttle_events:
            return False
        dev = data.get("device_id")
        iface = data.get("interface")
        if dev is not None and iface:
            key = f"{event}:{dev}:{iface}"
        elif dev is not None:
            key = f"{event}:{dev}"
        else:
            key = event
        now = time.monotonic()
        with self._lock:
            last = self._last_sent.get(key, 0.0)
            if last and (now - last) < self._throttle_sec:
                return True
            self._last_sent[key] = now
        return False

    def _publish_local(self, event: str, data: Dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subscribers)
        if not subs:
            return
        msg = RealtimeEvent(event=event, data=data)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(msg)
                except Exception:
                    pass

    def _ensure_redis_listener(self) -> None:
        if self._redis_thread is not None:
            return
        if redis is None:
            return
        try:
            self._redis_client = redis.Redis.from_url(self._redis_url)
            pubsub = self._redis_client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(self._redis_channel)
        except Exception:
            self._redis_client = None
            return

        def _run():
            try:
                for msg in pubsub.listen():
                    if self._redis_stop.is_set():
                        break
                    if not isinstance(msg, dict) or msg.get("type") != "message":
                        continue
                    raw = msg.get("data")
                    if raw is None:
                        continue
                    try:
                        if isinstance(raw, (bytes, bytearray)):
                            raw = raw.decode("utf-8", errors="ignore")
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    if payload.get("origin") == self._origin:
                        continue
                    ev = payload.get("event")
                    data = payload.get("data")
                    if isinstance(ev, str) and isinstance(data, dict):
                        self._publish_local(ev, data)
            finally:
                try:
                    pubsub.close()
                except Exception:
                    pass

        self._redis_thread = threading.Thread(target=_run, daemon=True)
        self._redis_thread.start()

    def _publish_redis(self, event: str, data: Dict[str, Any]) -> None:
        if redis is None:
            return
        try:
            if self._redis_client is None:
                self._redis_client = redis.Redis.from_url(self._redis_url)
            payload = {"event": event, "data": data, "origin": self._origin}
            self._redis_client.publish(self._redis_channel, json.dumps(payload, ensure_ascii=False))
        except Exception:
            return


realtime_event_bus = RealtimeEventBus()
