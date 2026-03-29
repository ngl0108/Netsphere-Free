import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, ConfigBackup


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_deploy_worker_rolls_back_and_saves_backup(monkeypatch, db_engine):
    from app.api.v1.endpoints import config_template as ct

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(ct, "SessionLocal", SessionLocal)

    db = SessionLocal()
    d = Device(name="sw1", ip_address="10.0.0.1")
    db.add(d)
    db.commit()
    db.refresh(d)
    db.close()

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
            return "hostname before"

        def send_config_set(self, commands):
            raise Exception("push failed")

        def send_command(self, command, **kwargs):
            return "ok"

    monkeypatch.setattr(ct, "DeviceConnection", FakeConn)

    res = ct._deploy_worker(
        {
            "dev_id": d.id,
            "context": {"device": {"name": "sw1", "ip": "10.0.0.1"}},
            "device_info_args": {"host": "10.0.0.1", "username": "u", "password": "p", "secret": None, "port": 22, "device_type": "cisco_ios"},
        },
        "hostname {{ device.name }}",
        {"save_pre_backup": True, "rollback_on_failure": True, "prepare_device_snapshot": True},
    )

    assert res["status"] == "failed"
    assert res["rollback_attempted"] is True
    assert res["rollback_success"] is True
    assert res["backup_id"] is not None


def test_deploy_worker_post_check_failure_triggers_rollback(monkeypatch, db_engine):
    from app.api.v1.endpoints import config_template as ct

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(ct, "SessionLocal", SessionLocal)

    db = SessionLocal()
    d = Device(name="sw1", ip_address="10.0.0.1")
    db.add(d)
    db.commit()
    db.refresh(d)
    db.close()

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
            return "hostname before"

        def send_config_set(self, commands):
            return "ok"

        def send_command(self, command, **kwargs):
            return "% Invalid input detected"

    monkeypatch.setattr(ct, "DeviceConnection", FakeConn)

    res = ct._deploy_worker(
        {
            "dev_id": d.id,
            "context": {"device": {"name": "sw1", "ip": "10.0.0.1"}},
            "device_info_args": {"host": "10.0.0.1", "username": "u", "password": "p", "secret": None, "port": 22, "device_type": "cisco_ios"},
        },
        "hostname {{ device.name }}",
        {"save_pre_backup": True, "rollback_on_failure": True, "prepare_device_snapshot": True, "post_check_enabled": True, "post_check_commands": ["show clock"]},
    )

    assert res["status"] == "postcheck_failed"
    assert (res.get("post_check") or {}).get("ok") is False
    assert res["rollback_attempted"] is True
    assert res["rollback_success"] is True


def test_post_check_profile_resolves_from_settings(monkeypatch, db_engine):
    from app.api.v1.endpoints import config_template as ct
    from app.models.settings import SystemSetting

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(ct, "SessionLocal", SessionLocal)

    db = SessionLocal()
    d = Device(name="sw1", ip_address="10.0.0.1", role="access", device_type="dasan_nos")
    db.add(d)
    db.commit()
    db.refresh(d)
    dev_id = int(d.id)
    db.add(SystemSetting(key="post_check_role_access", value='["show version"]', description="", category="post_check"))
    db.commit()
    db.close()

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
            return "hostname before"

        def send_config_set(self, commands):
            return "ok"

        def send_command(self, command, **kwargs):
            if command == "show version":
                return "ok"
            return "% invalid input"

    monkeypatch.setattr(ct, "DeviceConnection", FakeConn)

    res = ct._deploy_worker(
        {
            "dev_id": dev_id,
            "context": {"device": {"name": "sw1", "ip": "10.0.0.1"}},
            "device_info_args": {"host": "10.0.0.1", "username": "u", "password": "p", "secret": None, "port": 22, "device_type": "dasan_nos"},
        },
        "hostname {{ device.name }}",
        {"save_pre_backup": False, "rollback_on_failure": True, "prepare_device_snapshot": True, "post_check_enabled": True, "post_check_commands": []},
    )

    assert res["status"] == "success"
    assert res["post_check"]["command"] == "show version"
