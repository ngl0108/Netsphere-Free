import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Issue, Link, SystemMetric
from app.services.smart_alerting_service import (
    DynamicThresholdConfig,
    run_alert_correlation,
    run_dynamic_threshold_alerts,
)


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


def test_dynamic_threshold_creates_cpu_spike_issue(db):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d = Device(name="sw1", ip_address="10.0.0.1")
    db.add(d)
    db.commit()
    db.refresh(d)

    for i in range(5):
        db.add(
            SystemMetric(
                device_id=d.id,
                cpu_usage=50.0,
                memory_usage=40.0,
                traffic_in=1_000_000.0,
                traffic_out=1_000_000.0,
                timestamp=now - timedelta(days=2, minutes=i),
            )
        )
    db.add(
        SystemMetric(
            device_id=d.id,
            cpu_usage=80.0,
            memory_usage=40.0,
            traffic_in=1_000_000.0,
            traffic_out=1_000_000.0,
            timestamp=now - timedelta(minutes=1),
        )
    )
    db.commit()

    cfg = DynamicThresholdConfig(baseline_days=7, exclude_recent_minutes=10, cpu_spike_ratio=0.30, cpu_min_abs=50.0)
    res = run_dynamic_threshold_alerts(db, cfg=cfg, now=now)
    db.commit()

    assert res["created"] >= 1
    issue = db.query(Issue).filter(Issue.device_id == d.id, Issue.title.like("Dynamic CPU Spike:%")).first()
    assert issue is not None


def test_alert_correlation_creates_root_cause_issue(db):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d = Device(name="sw1", ip_address="10.0.0.1")
    db.add(d)
    db.commit()
    db.refresh(d)

    db.add(Issue(device_id=d.id, title="BGP Neighbor Down: sw1", description="", severity="warning", status="active", category="system", created_at=now - timedelta(minutes=2)))
    db.add(Issue(device_id=d.id, title="Interface Errors (Gi1/0/1)", description="", severity="warning", status="active", category="performance", created_at=now - timedelta(minutes=1)))
    db.add(Issue(device_id=d.id, title="Dynamic Traffic Drop: sw1", description="", severity="warning", status="active", category="performance", created_at=now - timedelta(minutes=1)))
    db.commit()

    res = run_alert_correlation(db, now=now, window_minutes=15)
    db.commit()

    assert res["created"] == 1
    root = db.query(Issue).filter(Issue.device_id == d.id, Issue.title.like("Root Cause Suspected:%")).first()
    assert root is not None


def test_alert_correlation_matches_link_down_bgp_down_and_degraded(db):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = Device(name="sw1", ip_address="10.0.0.1")
    d2 = Device(name="sw2", ip_address="10.0.0.2")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(Issue(device_id=d1.id, title="BGP Neighbor Down: sw1", description="", severity="warning", status="active", category="system", created_at=now - timedelta(minutes=2)))
    db.add(Issue(device_id=d1.id, title="Interface Drops (Gi1/0/2)", description="", severity="warning", status="active", category="performance", created_at=now - timedelta(minutes=1)))
    db.add(
        Link(
            source_device_id=d1.id,
            target_device_id=d2.id,
            source_interface_name="Gi1/0/2",
            target_interface_name="Gi1/0/2",
            status="down",
            protocol="LLDP",
            last_seen=now - timedelta(minutes=1),
        )
    )
    db.commit()

    res = run_alert_correlation(db, now=now, window_minutes=15)
    db.commit()

    assert res["created"] == 1
