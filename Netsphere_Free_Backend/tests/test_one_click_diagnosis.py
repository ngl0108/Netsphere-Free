import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Issue, Link, SystemMetric
from app.services.diagnosis_service import OneClickDiagnosisOptions, OneClickDiagnosisService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_one_click_diagnosis_marks_link_down_abnormal(db, monkeypatch):
    d1 = Device(name="sw1", ip_address="10.0.0.1")
    d2 = Device(name="sw2", ip_address="10.0.0.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(
        Link(
            source_device_id=d1.id,
            target_device_id=d2.id,
            source_interface_name="Gi1/0/1",
            target_interface_name="Gi1/0/1",
            status="down",
            protocol="LLDP",
        )
    )
    db.commit()

    fake_trace = {
        "status": "success",
        "mode": "bfs",
        "path": [
            {"id": d1.id, "ingress_intf": "Client", "egress_intf": "Gi1/0/1"},
            {"id": d2.id, "ingress_intf": "Gi1/0/1", "egress_intf": "Host"},
        ],
        "path_node_ids": [d1.id, d2.id],
        "segments": [
            {
                "hop": 0,
                "from_id": d1.id,
                "to_id": d2.id,
                "from_port": "Gi1/0/1",
                "to_port": "Gi1/0/1",
                "link": {
                    "id": 1,
                    "status": "down",
                    "source_device_id": d1.id,
                    "target_device_id": d2.id,
                    "source_interface_name": "Gi1/0/1",
                    "target_interface_name": "Gi1/0/1",
                },
            }
        ],
    }

    from app.services import path_trace_service as pts

    monkeypatch.setattr(pts.PathTraceService, "trace_path", lambda self, src_ip, dst_ip: fake_trace)
    monkeypatch.setattr("app.services.diagnosis_service._ping_once", lambda ip, timeout_ms=1000: True)

    res = OneClickDiagnosisService(db).run(
        "192.0.2.1",
        "198.51.100.2",
        options=OneClickDiagnosisOptions(include_show_commands=False),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert res["ok"] is True
    assert res["summary"]["abnormal_count"] >= 1
    assert any(a.get("type") == "link" for a in res.get("abnormal") or [])


def test_one_click_diagnosis_marks_link_degraded_abnormal(db, monkeypatch):
    d1 = Device(name="sw1", ip_address="10.0.1.1")
    d2 = Device(name="sw2", ip_address="10.0.1.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(
        Link(
            source_device_id=d1.id,
            target_device_id=d2.id,
            source_interface_name="Gi1/0/1",
            target_interface_name="Gi1/0/1",
            status="degraded",
            protocol="LLDP",
        )
    )
    db.commit()

    fake_trace = {
        "status": "success",
        "mode": "topology_best_effort",
        "path": [
            {"id": d1.id, "ingress_intf": "Client", "egress_intf": "Gi1/0/1"},
            {"id": d2.id, "ingress_intf": "Gi1/0/1", "egress_intf": "Host"},
        ],
        "path_node_ids": [d1.id, d2.id],
        "segments": [
            {
                "hop": 0,
                "from_id": d1.id,
                "to_id": d2.id,
                "from_port": "Gi1/0/1",
                "to_port": "Gi1/0/1",
                "status": "degraded",
                "link": {
                    "id": 1,
                    "status": "degraded",
                    "source_device_id": d1.id,
                    "target_device_id": d2.id,
                    "source_interface_name": "Gi1/0/1",
                    "target_interface_name": "Gi1/0/1",
                },
            }
        ],
    }

    from app.services import path_trace_service as pts

    monkeypatch.setattr(pts.PathTraceService, "trace_path", lambda self, src_ip, dst_ip: fake_trace)
    monkeypatch.setattr("app.services.diagnosis_service._ping_once", lambda ip, timeout_ms=1000: True)

    res = OneClickDiagnosisService(db).run(
        "192.0.2.10",
        "198.51.100.10",
        options=OneClickDiagnosisOptions(include_show_commands=False),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert res["ok"] is True
    assert res["summary"]["abnormal_count"] >= 1
    assert any(a.get("type") == "link" for a in res.get("abnormal") or [])


def test_one_click_diagnosis_enriches_bgp_abnormal_and_show_plan(db, monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = Device(name="edge1", ip_address="10.10.0.1", ssh_password="pw", device_type="cisco_ios")
    d2 = Device(name="edge2", ip_address="10.10.0.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(SystemMetric(device_id=d1.id, cpu_usage=82.5, memory_usage=63.2, traffic_in=100.0, traffic_out=90.0, timestamp=now))
    db.add(
        Issue(
            device_id=d1.id,
            title="BGP Neighbor Down",
            description="peer 10.10.0.2 idle",
            severity="warning",
            status="active",
            category="system",
            created_at=now,
        )
    )
    db.commit()

    fake_trace = {
        "status": "success",
        "mode": "topology_best_effort",
        "path": [
            {"id": d1.id, "ingress_intf": "Vlan10", "egress_intf": "Gi0/1"},
            {"id": d2.id, "ingress_intf": "Gi0/1", "egress_intf": "Host"},
        ],
        "path_node_ids": [d1.id, d2.id],
        "segments": [
            {
                "hop": 0,
                "from_id": d1.id,
                "to_id": d2.id,
                "from_port": "Gi0/1",
                "to_port": "Gi0/1",
                "status": "degraded",
                "protocol": "BGP",
                "layer": "l3",
                "link": {
                    "id": 77,
                    "status": "degraded",
                    "protocol": "BGP",
                    "layer": "l3",
                },
            }
        ],
        "summary": {
            "health": "degraded",
            "warnings": ["Used best-effort topology path with degraded links."],
            "protocols": ["BGP"],
            "layers": ["l3"],
            "complete": True,
        },
    }

    from app.services import path_trace_service as pts
    from app.services import diagnosis_service as ds

    monkeypatch.setattr(pts.PathTraceService, "trace_path", lambda self, src_ip, dst_ip: fake_trace)
    monkeypatch.setattr("app.services.diagnosis_service._ping_once", lambda ip, timeout_ms=1000: True)
    monkeypatch.setattr(ds, "_run_show_commands", lambda device, commands, timeout_sec: {cmd: f"{cmd} ok" for cmd in commands})

    res = OneClickDiagnosisService(db).run(
        "192.0.2.11",
        "198.51.100.11",
        options=OneClickDiagnosisOptions(include_show_commands=True, max_show_devices=1),
        now=now,
    )

    assert res["ok"] is True
    assert res["summary"]["severity"] == "warning"
    assert res["summary"]["root_cause"] == "bgp_session_degraded"
    assert res["diagnosis"]["verdict"] == "bgp_session_degraded"
    assert res["abnormal"][0]["root_cause"] == "bgp_session_degraded"
    assert res["abnormal"][0]["segment"]["protocol"] == "BGP"
    assert any(e.get("label") == "Protocol" and e.get("value") == "BGP" for e in res["abnormal"][0]["evidence"])
    assert res["device_health"][0]["risk_level"] == "warning"
    assert res["device_health"][0]["health_score"] < 100
    assert any("bgp" in item.get("command", "").lower() for item in res["show"][0]["plan"])
    assert any(item.get("purpose") for item in res["show"][0]["results"])


def test_one_click_diagnosis_marks_unreachable_device_as_critical_with_guidance(db, monkeypatch):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = Device(name="agg1", ip_address="10.20.0.1")
    d2 = Device(name="agg2", ip_address="10.20.0.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    fake_trace = {
        "status": "success",
        "mode": "bfs",
        "path": [
            {"id": d1.id, "ingress_intf": "Client", "egress_intf": "Gi0/1"},
            {"id": d2.id, "ingress_intf": "Gi0/1", "egress_intf": "Host"},
        ],
        "path_node_ids": [d1.id, d2.id],
        "segments": [
            {
                "hop": 0,
                "from_id": d1.id,
                "to_id": d2.id,
                "from_port": "Gi0/1",
                "to_port": "Gi0/1",
                "status": "active",
                "protocol": "LLDP",
                "layer": "l2",
                "link": {
                    "id": 91,
                    "status": "active",
                    "protocol": "LLDP",
                    "layer": "l2",
                },
            }
        ],
        "summary": {"health": "healthy", "complete": True},
    }

    from app.services import path_trace_service as pts

    monkeypatch.setattr(pts.PathTraceService, "trace_path", lambda self, src_ip, dst_ip: fake_trace)
    monkeypatch.setattr("app.services.diagnosis_service._ping_once", lambda ip, timeout_ms=1000: ip != "10.20.0.1")

    res = OneClickDiagnosisService(db).run(
        "192.0.2.21",
        "198.51.100.21",
        options=OneClickDiagnosisOptions(include_show_commands=False),
        now=now,
    )

    assert res["ok"] is True
    assert res["summary"]["severity"] == "critical"
    assert res["summary"]["root_cause"] == "device_unreachable"
    assert res["diagnosis"]["verdict"] == "device_unreachable"
    assert res["abnormal"][0]["type"] == "ping"
    assert res["abnormal"][0]["next_actions"]
    assert res["device_health"][0]["risk_level"] == "critical"
    assert res["device_health"][0]["primary_signal"] == "reachability"
