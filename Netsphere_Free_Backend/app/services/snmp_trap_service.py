import threading
from datetime import datetime
import asyncio

from app.db.session import SessionLocal
from app.models.device import Device, Interface, Link
from app.services.snmp_service import SnmpManager

from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import ntfrcv
try:
    from pysnmp.carrier.asyncio.dgram import udp
    from pysnmp.carrier.asyncio.dispatch import AsyncioDispatcher
    _DISPATCHER_KIND = "asyncio"
except Exception:
    from pysnmp.carrier.asyncore.dgram import udp
    AsyncioDispatcher = None
    _DISPATCHER_KIND = "asyncore"


class SnmpTrapServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 162, community: str = "public"):
        self.host = host
        self.port = int(port or 162)
        self.community = str(community or "public")
        self._thread = None
        self._snmp_engine = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        snmp_engine = engine.SnmpEngine()
        self._snmp_engine = snmp_engine
        if _DISPATCHER_KIND == "asyncio" and AsyncioDispatcher is not None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            snmp_engine.register_transport_dispatcher(AsyncioDispatcher())

        add_transport = getattr(config, "add_transport", getattr(config, "addTransport"))
        add_v1_system = getattr(config, "add_v1_system", getattr(config, "addV1System"))
        add_vacm_user = getattr(config, "add_vacm_user", getattr(config, "addVacmUser"))

        open_server = getattr(udp.UdpTransport(), "open_server_mode", getattr(udp.UdpTransport(), "openServerMode"))

        add_transport(snmp_engine, udp.domainName, open_server((self.host, self.port)))
        add_v1_system(snmp_engine, "trap-community", self.community)
        add_vacm_user(snmp_engine, 2, "trap-community", "noAuthNoPriv", (1, 3, 6), (1, 3, 6))

        def cb_fun(snmp_engine, state_reference, context_engine_id, context_name, var_binds, cb_ctx):
            try:
                transport_domain, transport_address = snmp_engine.msgAndPduDsp.getTransportInfo(state_reference)
                source_ip = str(transport_address[0])
            except Exception:
                source_ip = ""

            trap_oid = ""
            if_index = None
            for oid, val in var_binds:
                oid_s = str(oid)
                if oid_s == "1.3.6.1.6.3.1.1.4.1.0":
                    trap_oid = str(val)
                if oid_s.startswith("1.3.6.1.2.1.2.2.1.1."):
                    try:
                        if_index = int(oid_s.split(".")[-1])
                    except Exception:
                        pass

            if trap_oid not in ("1.3.6.1.6.3.1.1.5.3", "1.3.6.1.6.3.1.1.5.4"):
                return
            if not source_ip or if_index is None:
                return

            is_up = trap_oid.endswith(".3")
            new_state = "up" if is_up else "down"

            db = SessionLocal()
            try:
                device = db.query(Device).filter(Device.ip_address == source_ip).first()
                if not device:
                    return

                snmp = SnmpManager(
                    device.ip_address,
                    community=device.snmp_community,
                    port=int(device.snmp_port or 161),
                    version=str(device.snmp_version or "v2c"),
                    v3_username=device.snmp_v3_username,
                    v3_security_level=device.snmp_v3_security_level,
                    v3_auth_proto=device.snmp_v3_auth_proto,
                    v3_auth_key=device.snmp_v3_auth_key,
                    v3_priv_proto=device.snmp_v3_priv_proto,
                    v3_priv_key=device.snmp_v3_priv_key,
                )
                if_name = ""
                oid = f"1.3.6.1.2.1.31.1.1.1.1.{if_index}"
                res = snmp.get_oids([oid]) or {}
                if_name = str(res.get(oid) or "").strip()
                if not if_name:
                    oid2 = f"1.3.6.1.2.1.2.2.1.2.{if_index}"
                    res2 = snmp.get_oids([oid2]) or {}
                    if_name = str(res2.get(oid2) or "").strip()
                if not if_name:
                    return

                target_if = (
                    db.query(Interface)
                    .filter(Interface.device_id == device.id, Interface.name == if_name)
                    .first()
                )
                if target_if:
                    target_if.status = new_state

                now = datetime.now()
                def _n(x: str) -> str:
                    return str(x or "").strip().lower().replace(" ", "")
                normalized_if = _n(if_name)
                touched = []
                links = db.query(Link).filter(
                    (Link.source_device_id == device.id) | (Link.target_device_id == device.id)
                ).all()
                for l in links:
                    if l.source_device_id == device.id and _n(l.source_interface_name) == normalized_if:
                        l.status = "up" if is_up else "down"
                        l.last_seen = now
                        touched.append(l.id)
                    elif l.target_device_id == device.id and _n(l.target_interface_name) == normalized_if:
                        l.status = "up" if is_up else "down"
                        l.last_seen = now
                        touched.append(l.id)
                db.commit()

                if touched:
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
                                "source": "snmp_trap",
                            },
                        )
                    except Exception:
                        pass
            finally:
                db.close()

        ntfrcv.NotificationReceiver(snmp_engine, cb_fun)
        td = getattr(snmp_engine, "transport_dispatcher", None) or getattr(snmp_engine, "transportDispatcher", None)
        if td:
            job_started = getattr(td, "job_started", getattr(td, "jobStarted", None))
            if job_started:
                job_started(1)
        try:
            if td:
                run_dispatcher = getattr(td, "run_dispatcher", getattr(td, "runDispatcher"))
                run_dispatcher()
        except Exception:
            try:
                if td:
                    close_dispatcher = getattr(td, "close_dispatcher", getattr(td, "closeDispatcher"))
                    close_dispatcher()
            except Exception:
                pass
