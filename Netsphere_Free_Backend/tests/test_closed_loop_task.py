import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.approval import ApprovalRequest
from app.models.device import Device, EventLog, SystemMetric
from app.models.settings import SystemSetting
from app.models import approval as _approval
from app.models import device as _device
from app.models import settings as _settings
from app.models import tenant as _tenant
from app.models import user as _user


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def _set_setting(db, key: str, value: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value=str(value), description=key, category="system")
    else:
        row.value = str(value)
    db.add(row)
    db.commit()
    return row


def _set_rules(db, rules):
    _set_setting(db, "closed_loop_rules_json", json.dumps(list(rules or []), ensure_ascii=False))


def _cpu_rule(rule_id: str = "r-cpu-high", require_approval: bool = True):
    return {
        "id": rule_id,
        "name": "CPU High",
        "enabled": True,
        "condition": {"path": "summary.cpu_avg", "operator": ">=", "value": 80},
        "action": {"type": "notify", "title": "CPU High", "message": "threshold reached"},
        "require_approval": bool(require_approval),
        "cooldown_seconds": 600,
        "max_actions_per_hour": 5,
    }


def test_closed_loop_cycle_skips_when_engine_disabled(monkeypatch, db_engine):
    from app.tasks import closed_loop as task_mod

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_mod, "SessionLocal", SessionLocal)

    out = task_mod.run_closed_loop_cycle()
    assert out["status"] == "skipped"
    assert out["reason"] == "engine_disabled"


def test_closed_loop_cycle_runs_but_does_not_execute_when_auto_disabled(monkeypatch, db_engine):
    from app.tasks import closed_loop as task_mod

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_mod, "SessionLocal", SessionLocal)

    db = SessionLocal()
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "false")
    _set_rules(db, [_cpu_rule(require_approval=True)])
    dev = Device(name="cl-dev-1", ip_address="10.66.0.1", status="online", device_type="cisco_ios")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    db.add(SystemMetric(device_id=int(dev.id), cpu_usage=95.0, memory_usage=40.0, traffic_in=100, traffic_out=100))
    db.commit()
    db.close()

    out = task_mod.run_closed_loop_cycle()
    assert out["status"] == "ok"
    assert int(out["triggered"]) == 1
    assert int(out["executed"]) == 0
    assert int(out["blocked"]) == 0
    rows = list(out.get("decisions") or [])
    assert len(rows) == 1
    assert rows[0]["status"] == "matched_auto_execute_disabled"

    db = SessionLocal()
    assert db.query(ApprovalRequest).count() == 0
    logs = db.query(EventLog).filter(EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY").all()
    assert len(logs) == 1
    db.close()


def test_closed_loop_cycle_executes_and_creates_approval_when_auto_enabled(monkeypatch, db_engine):
    from app.tasks import closed_loop as task_mod

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_mod, "SessionLocal", SessionLocal)

    db = SessionLocal()
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_rules(db, [_cpu_rule(require_approval=True)])
    dev = Device(name="cl-dev-2", ip_address="10.66.0.2", status="online", device_type="cisco_ios")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    db.add(SystemMetric(device_id=int(dev.id), cpu_usage=92.0, memory_usage=35.0, traffic_in=200, traffic_out=120))
    db.commit()
    db.close()

    out = task_mod.run_closed_loop_cycle()
    assert out["status"] == "ok"
    assert int(out["triggered"]) == 1
    assert int(out["executed"]) == 1
    assert int(out["approvals_opened"]) == 1

    db = SessionLocal()
    reqs = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "closed_loop_action").all()
    assert len(reqs) == 1
    payload = dict(reqs[0].payload or {})
    assert str(payload.get("source")) == "closed_loop"
    assert str(payload.get("rule_id")) == "r-cpu-high"
    db.close()
