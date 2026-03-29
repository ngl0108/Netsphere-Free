from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.cloud import CloudAccount
from app.models.settings import SystemSetting


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_cloud_auto_sync_skips_when_disabled(monkeypatch, db_engine):
    from app.tasks import cloud_sync as task_module
    from app.services.ha_service import HaService

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(HaService, "enabled", staticmethod(lambda _db: False))
    monkeypatch.setattr(HaService, "is_active", staticmethod(lambda _db: True))

    db = SessionLocal()
    db.add(SystemSetting(key="cloud_auto_sync_enabled", value="false", description="", category="General"))
    db.commit()
    db.close()

    out = task_module.run_cloud_auto_sync()
    assert out["status"] == "skipped"
    assert out["reason"] == "disabled"


def test_cloud_auto_sync_runs_for_stale_accounts(monkeypatch, db_engine):
    from app.tasks import cloud_sync as task_module
    from app.services.ha_service import HaService
    from app.services.cloud_pipeline_service import CloudPipelineService

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(HaService, "enabled", staticmethod(lambda _db: False))
    monkeypatch.setattr(HaService, "is_active", staticmethod(lambda _db: True))

    db = SessionLocal()
    db.add(SystemSetting(key="cloud_auto_sync_enabled", value="true", description="", category="General"))
    db.add(SystemSetting(key="cloud_auto_sync_interval_seconds", value="60", description="", category="General"))
    stale = CloudAccount(
        name="ncp-stale",
        provider="ncp",
        credentials={"access_key": "x", "secret_key": "y"},
        is_active=True,
        tenant_id=None,
        last_synced_at=datetime.utcnow() - timedelta(minutes=10),
    )
    fresh = CloudAccount(
        name="aws-fresh",
        provider="aws",
        credentials={"access_key": "x", "secret_key": "y", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
        last_synced_at=datetime.utcnow(),
    )
    db.add_all([stale, fresh])
    db.commit()
    stale_id = int(stale.id)
    fresh_id = int(fresh.id)
    db.close()

    captured = {}

    def _fake_run(db, *, tenant_id, owner_id, req):
        captured["tenant_id"] = tenant_id
        captured["owner_id"] = owner_id
        captured["account_ids"] = list(req.account_ids or [])
        captured["preflight"] = bool(req.preflight)
        return SimpleNamespace(status="ok", total_accounts=1, scanned_resources=4, failed_accounts=0)

    monkeypatch.setattr(CloudPipelineService, "run", staticmethod(_fake_run))

    out = task_module.run_cloud_auto_sync()
    assert out["status"] == "ok"
    assert out["accounts"] == 1
    assert out["scanned_resources"] == 4
    assert out["failed_accounts"] == 0
    assert out["account_ids"] == [stale_id]
    assert captured["account_ids"] == [stale_id]
    assert fresh_id not in captured["account_ids"]
    assert captured["tenant_id"] is None
    assert captured["owner_id"] == 0

    db = SessionLocal()
    lock_row = db.query(SystemSetting).filter(SystemSetting.key == "cloud_auto_sync_lock").first()
    assert lock_row is not None
    assert (lock_row.value or "") == ""
    db.close()


def test_cloud_auto_sync_skips_when_lock_held(monkeypatch, db_engine):
    from app.tasks import cloud_sync as task_module
    from app.services.ha_service import HaService
    from app.services.cloud_pipeline_service import CloudPipelineService

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(HaService, "enabled", staticmethod(lambda _db: False))
    monkeypatch.setattr(HaService, "is_active", staticmethod(lambda _db: True))

    db = SessionLocal()
    db.add(SystemSetting(key="cloud_auto_sync_enabled", value="true", description="", category="General"))
    db.add(SystemSetting(key="cloud_auto_sync_interval_seconds", value="60", description="", category="General"))
    db.add(
        SystemSetting(
            key="cloud_auto_sync_lock",
            value=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
            description="cloud_auto_sync_lock",
            category="system",
        )
    )
    db.add(
        CloudAccount(
            name="aws-stale",
            provider="aws",
            credentials={"access_key": "x", "secret_key": "y", "region": "ap-northeast-2"},
            is_active=True,
            tenant_id=None,
            last_synced_at=datetime.utcnow() - timedelta(minutes=10),
        )
    )
    db.commit()
    db.close()

    def _unexpected_run(*args, **kwargs):
        raise AssertionError("CloudPipelineService.run should not execute when the sync lock is held")

    monkeypatch.setattr(CloudPipelineService, "run", staticmethod(_unexpected_run))

    out = task_module.run_cloud_auto_sync()
    assert out["status"] == "skipped"
    assert out["reason"] == "lock_held"
