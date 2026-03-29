import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, ConfigBackup, EventLog
from app.services.compliance_service import ComplianceEngine


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


def test_remediate_config_drift_applies_golden_and_becomes_compliant(db, monkeypatch):
    dev = Device(
        name="sw1",
        ip_address="10.0.0.1",
        device_type="dasan_nos",
        role="access",
        ssh_username="u",
        ssh_password="p",
        ssh_port=22,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)

    golden_text = "hostname sw1\ninterface Gi1/0/1\n description test\n"
    db.add(ConfigBackup(device_id=dev.id, raw_config=golden_text, is_golden=True))
    db.add(ConfigBackup(device_id=dev.id, raw_config="hostname old\n", is_golden=False))
    db.commit()

    from app.services import compliance_service as cs

    class FakeDriver:
        def __init__(self):
            self._rollback_ref = None

        def prepare_rollback(self, name: str) -> bool:
            self._rollback_ref = name
            return True

        def rollback(self) -> bool:
            return True

    class FakeConn:
        def __init__(self, info):
            self.driver = FakeDriver()
            self.last_error = None
            self._applied = False

        def connect(self):
            return True

        def disconnect(self):
            return None

        def get_running_config(self):
            return golden_text if self._applied else "hostname old\n"

        def send_config_set(self, commands):
            self._applied = True
            return "ok"

        def send_command(self, command, **kwargs):
            return "ok"

    monkeypatch.setattr(cs, "DeviceConnection", FakeConn)

    res = ComplianceEngine(db).remediate_config_drift(dev.id, post_check_enabled=True)
    assert res["status"] == "ok"
    assert res["drift_after"]["status"] == "compliant"


def test_remediate_prefers_config_replace_when_supported(db, monkeypatch):
    dev = Device(
        name="sw1",
        ip_address="10.0.0.1",
        device_type="cisco_ios",
        role="core",
        ssh_username="u",
        ssh_password="p",
        ssh_port=22,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)

    golden_text = "hostname sw1\n"
    db.add(ConfigBackup(device_id=dev.id, raw_config=golden_text, is_golden=True))
    db.add(ConfigBackup(device_id=dev.id, raw_config="hostname old\n", is_golden=False))
    db.commit()

    from app.services import compliance_service as cs

    class FakeDriver:
        def __init__(self):
            self._rollback_ref = None
            self._applied = False

        def prepare_rollback(self, name: str) -> bool:
            self._rollback_ref = name
            return True

        def rollback(self) -> bool:
            return True

        def apply_config_replace(self, raw_config: str):
            self._applied = True
            return {"success": True, "output": "replaced"}

    class FakeConn:
        def __init__(self, info):
            self.driver = FakeDriver()
            self.last_error = None

        def connect(self):
            return True

        def disconnect(self):
            return None

        def get_running_config(self):
            return golden_text if self.driver._applied else "hostname old\n"

        def send_config_set(self, commands):
            raise AssertionError("send_config_set should not be used when config replace is supported")

        def send_command(self, command, **kwargs):
            return "ok"

    monkeypatch.setattr(cs, "DeviceConnection", FakeConn)

    res = ComplianceEngine(db).remediate_config_drift(dev.id, post_check_enabled=False)
    assert res["status"] == "ok"
    assert res.get("replace_result", {}).get("success") is True


def test_remediate_pre_check_failure_blocks_deploy_and_marks_precheck_failed(db, monkeypatch):
    dev = Device(
        name="sw-precheck",
        ip_address="10.0.0.3",
        device_type="cisco_ios",
        role="access",
        ssh_username="u",
        ssh_password="p",
        ssh_port=22,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)

    golden_text = "hostname sw-precheck\n"
    db.add(ConfigBackup(device_id=dev.id, raw_config=golden_text, is_golden=True))
    db.add(ConfigBackup(device_id=dev.id, raw_config="hostname old\n", is_golden=False))
    db.commit()

    from app.services import compliance_service as cs

    class FakeDriver:
        def __init__(self):
            self._rollback_ref = None

        def prepare_rollback(self, name: str) -> bool:
            self._rollback_ref = name
            return True

        def rollback(self) -> bool:
            return True

    class FakeConn:
        def __init__(self, info):
            self.driver = FakeDriver()
            self.last_error = None

        def connect(self):
            return True

        def disconnect(self):
            return None

        def get_running_config(self):
            return "hostname old\n"

        def send_config_set(self, commands):
            raise AssertionError("send_config_set should not run when pre-check fails")

        def send_command(self, command, **kwargs):
            return "% Invalid input detected"

    monkeypatch.setattr(cs, "DeviceConnection", FakeConn)

    res = ComplianceEngine(db).remediate_config_drift(
        dev.id,
        pre_check_commands=["show version"],
        post_check_enabled=False,
    )
    assert res["status"] == "precheck_failed"
    assert bool((res.get("pre_check") or {}).get("ok")) is False
    assert str(res.get("failure_cause") or "") == "precheck_failed"
    assert bool(res.get("rollback_attempted")) is False

    kpi_row = (
        db.query(EventLog)
        .filter(EventLog.device_id == int(dev.id))
        .filter(EventLog.event_id == "CONFIG_DRIFT_REMEDIATION_KPI")
        .order_by(EventLog.timestamp.desc())
        .first()
    )
    assert kpi_row is not None
    payload = json.loads(str(kpi_row.message or "{}"))
    assert str(payload.get("status") or "") == "precheck_failed"
    assert str(payload.get("failure_cause") or "") == "precheck_failed"


def test_generic_driver_config_replace_smoke(monkeypatch):
    from app.drivers.generic_driver import GenericDriver

    class FakeConn:
        def __init__(self):
            self.calls = []

        def send_command_timing(self, cmd, **kwargs):
            self.calls.append(("timing", cmd))
            if cmd.startswith("copy terminal: primary:"):
                return "invalid input detected"
            if cmd.startswith("copy terminal:"):
                return "Enter configuration commands, one per line. End with CNTL/Z."
            if cmd == "\x1a":
                return "OK"
            if cmd.startswith("configure replace"):
                return "OK"
            return "OK"

        def send_command(self, cmd, **kwargs):
            self.calls.append(("cmd", cmd))
            return "OK"

    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn()
    d._config_replace_profile = {"file_systems": ["primary:", "flash:"]}
    res = d.apply_config_replace("hostname sw1\n")
    assert res["success"] is True
