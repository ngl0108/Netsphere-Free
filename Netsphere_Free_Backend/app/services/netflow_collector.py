from __future__ import annotations

import asyncio
import socket
import struct
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple


@dataclass(frozen=True)
class FlowEvent:
    ts: float
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    proto: int
    app: str
    bytes: int
    packets: int


def _ip(b: bytes) -> str:
    return socket.inet_ntoa(b)

_APP_BY_PROTO_PORT: Dict[Tuple[int, int], str] = {
    (6, 22): "SSH",
    (6, 23): "TELNET",
    (6, 25): "SMTP",
    (6, 80): "HTTP",
    (6, 110): "POP3",
    (6, 143): "IMAP",
    (6, 443): "HTTPS",
    (6, 445): "SMB",
    (6, 3389): "RDP",
    (6, 3306): "MYSQL",
    (6, 5432): "POSTGRES",
    (6, 6379): "REDIS",
    (6, 27017): "MONGODB",
    (17, 53): "DNS",
    (17, 67): "DHCP",
    (17, 68): "DHCP",
    (17, 123): "NTP",
    (17, 161): "SNMP",
    (17, 162): "SNMPTRAP",
    (17, 500): "IKE",
    (17, 514): "SYSLOG",
    (17, 1812): "RADIUS",
    (17, 1813): "RADIUS-ACCT",
}


def _guess_app(proto: int, src_port: int, dst_port: int) -> str:
    p = int(proto or 0)
    sp = int(src_port or 0)
    dp = int(dst_port or 0)
    if p == 1:
        return "ICMP"
    if (p, dp) in _APP_BY_PROTO_PORT:
        return _APP_BY_PROTO_PORT[(p, dp)]
    if (p, sp) in _APP_BY_PROTO_PORT:
        return _APP_BY_PROTO_PORT[(p, sp)]
    port = None
    if dp and dp <= 1024:
        port = dp
    elif sp and sp <= 1024:
        port = sp
    if port:
        return f"{'TCP' if p == 6 else 'UDP' if p == 17 else 'IP'}:{port}"
    return "OTHER"


class NetFlowV5Parser:
    HEADER_LEN = 24
    RECORD_LEN = 48

    @staticmethod
    def parse(payload: bytes) -> List[FlowEvent]:
        if len(payload) < NetFlowV5Parser.HEADER_LEN:
            return []
        ver, count = struct.unpack("!HH", payload[0:4])
        if ver != 5:
            return []
        if count <= 0:
            return []
        expected = NetFlowV5Parser.HEADER_LEN + count * NetFlowV5Parser.RECORD_LEN
        if len(payload) < expected:
            return []

        now = time.time()
        out: List[FlowEvent] = []
        off = NetFlowV5Parser.HEADER_LEN
        for _ in range(count):
            rec = payload[off : off + NetFlowV5Parser.RECORD_LEN]
            off += NetFlowV5Parser.RECORD_LEN
            try:
                srcaddr = _ip(rec[0:4])
                dstaddr = _ip(rec[4:8])
                d_pkts = struct.unpack("!I", rec[16:20])[0]
                d_octets = struct.unpack("!I", rec[20:24])[0]
                src_port = struct.unpack("!H", rec[32:34])[0]
                dst_port = struct.unpack("!H", rec[34:36])[0]
                proto = rec[38]
            except Exception:
                continue
            app = _guess_app(int(proto), int(src_port), int(dst_port))
            out.append(
                FlowEvent(
                    ts=now,
                    src_ip=srcaddr,
                    dst_ip=dstaddr,
                    src_port=int(src_port),
                    dst_port=int(dst_port),
                    proto=int(proto),
                    app=app,
                    bytes=int(d_octets),
                    packets=int(d_pkts),
                )
            )
        return out


class FlowStore:
    def __init__(self, max_events: int = 100_000):
        self._events: Deque[FlowEvent] = deque(maxlen=max_events)
        self._lock = asyncio.Lock()

    async def add_events(self, events: List[FlowEvent]) -> None:
        if not events:
            return
        async with self._lock:
            self._events.extend(events)

    async def top_talkers(self, window_sec: int = 300, limit: int = 10) -> List[Dict[str, object]]:
        now = time.time()
        cutoff = now - max(1, int(window_sec or 300))
        totals: Dict[str, int] = {}
        async with self._lock:
            for e in self._events:
                if e.ts < cutoff:
                    continue
                totals[e.src_ip] = totals.get(e.src_ip, 0) + int(e.bytes or 0)

        items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[: max(1, int(limit or 10))]
        window = max(1, int(window_sec or 300))
        return [{"src_ip": ip, "bytes": b, "bps": float(b * 8) / window} for ip, b in items]

    async def top_flows(self, window_sec: int = 300, limit: int = 10) -> List[Dict[str, object]]:
        now = time.time()
        cutoff = now - max(1, int(window_sec or 300))
        totals: Dict[Tuple[str, str, int, int, int, str], int] = {}
        async with self._lock:
            for e in self._events:
                if e.ts < cutoff:
                    continue
                k = (e.src_ip, e.dst_ip, e.src_port, e.dst_port, e.proto, e.app)
                totals[k] = totals.get(k, 0) + int(e.bytes or 0)

        items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[: max(1, int(limit or 10))]
        window = max(1, int(window_sec or 300))
        return [
            {
                "src_ip": k[0],
                "dst_ip": k[1],
                "src_port": k[2],
                "dst_port": k[3],
                "proto": k[4],
                "app": k[5],
                "bytes": b,
                "bps": float(b * 8) / window,
            }
            for k, b in items
        ]

    async def top_apps(self, window_sec: int = 300, limit: int = 10) -> List[Dict[str, object]]:
        now = time.time()
        cutoff = now - max(1, int(window_sec or 300))
        totals: Dict[str, int] = {}
        async with self._lock:
            for e in self._events:
                if e.ts < cutoff:
                    continue
                totals[e.app] = totals.get(e.app, 0) + int(e.bytes or 0)

        items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[: max(1, int(limit or 10))]
        window = max(1, int(window_sec or 300))
        return [{"app": app, "bytes": b, "bps": float(b * 8) / window} for app, b in items]

    async def top_app_flows(self, app: str, window_sec: int = 300, limit: int = 10) -> List[Dict[str, object]]:
        target = str(app or "").strip().upper()
        if not target:
            return []
        now = time.time()
        cutoff = now - max(1, int(window_sec or 300))
        totals: Dict[Tuple[str, str, int, int, int], int] = {}
        async with self._lock:
            for e in self._events:
                if e.ts < cutoff:
                    continue
                if str(e.app).upper() != target:
                    continue
                k = (e.src_ip, e.dst_ip, e.src_port, e.dst_port, e.proto)
                totals[k] = totals.get(k, 0) + int(e.bytes or 0)

        items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[: max(1, int(limit or 10))]
        window = max(1, int(window_sec or 300))
        return [
            {
                "src_ip": k[0],
                "dst_ip": k[1],
                "src_port": k[2],
                "dst_port": k[3],
                "proto": k[4],
                "bytes": b,
                "bps": float(b * 8) / window,
            }
            for k, b in items
        ]


flow_store = FlowStore()


class NetflowProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        try:
            events = NetFlowV5Parser.parse(data)
            if not events:
                return
            asyncio.create_task(flow_store.add_events(events))
        except Exception:
            return
