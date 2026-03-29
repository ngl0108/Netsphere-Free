import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
import secrets

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "test-field-encryption-key-for-pytest")

from app.main import app
from app.db.session import Base, get_db, get_async_db
from app.api import deps as api_deps
from app.db.migrations import run_migrations
from app.services.monitoring_profile_service import MonitoringProfileService

@pytest.fixture(scope="function")
def db_bundle():
    # Import all models to ensure they are registered with Base.metadata
    from app.models import (
        approval,
        asset_change_event,
        audit,
        automation,
        compliance,
        credentials,
        device,
        device_inventory,
        discovery,
        discovery_hint,
        discovery_hint_learning,
        email_verification,
        endpoint,
        ha_lease,
        image_job,
        license_state,
        mfa_challenge,
        monitoring_profile,
        settings,
        preview_collector_registration,
        preventive_check,
        service_group,
        topology,
        topology_candidate,
        user,
        user_password_history,
        user_session,
        visual_config,
        cloud,
        tenant,
        ip_intel,
        ztp_queue,
    )

    db_name = f"pytest_{secrets.token_hex(8)}"
    sync_url = f"sqlite:///file:{db_name}?mode=memory&cache=shared&uri=true"
    async_url = f"sqlite+aiosqlite:///file:{db_name}?mode=memory&cache=shared&uri=true"

    engine = create_engine(
        sync_url,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )
    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False, "uri": True},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    AsyncTestingSessionLocal = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    session = TestingSessionLocal()
    MonitoringProfileService.install_defaults(session)
    try:
        yield {"db": session, "async_sessionmaker": AsyncTestingSessionLocal}
    finally:
        session.close()
        try:
            Base.metadata.drop_all(bind=engine)
        finally:
            engine.dispose()
            try:
                async_engine.sync_engine.dispose()
            except Exception:
                pass

@pytest.fixture(scope="function")
def db(db_bundle):
    return db_bundle["db"]

@pytest.fixture(scope="function")
def client(db_bundle):
    db = db_bundle["db"]
    AsyncTestingSessionLocal = db_bundle["async_sessionmaker"]

    def override_get_db():
        try:
            yield db
        finally:
            pass

    async def override_get_async_db():
        async with AsyncTestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[api_deps.get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    yield TestClient(app)
    del app.dependency_overrides[get_db]
    del app.dependency_overrides[api_deps.get_db]
    del app.dependency_overrides[get_async_db]

@pytest.fixture
def auth_headers(client):
    return None

@pytest.fixture
def normal_user_token(db):
    from app.models.user import User
    from app.core.security import get_password_hash, create_access_token
    from app.services.session_service import SessionService
    
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=get_password_hash("testpass"),
        full_name="Test User",
        is_active=True,
        role="viewer"
    )
    db.add(user)
    db.commit()
    
    jti = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    SessionService.create(db, user_id=int(user.id), jti=jti, expires_at=expires_at)
    db.commit()
    access_token = create_access_token({"sub": user.username, "uid": int(user.id), "jti": jti})
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture
def admin_user_token(db):
    from app.models.user import User
    from app.core.security import get_password_hash, create_access_token
    from app.services.session_service import SessionService
    
    user = User(
        username="adminuser",
        email="admin@example.com",
        hashed_password=get_password_hash("adminpass"),
        full_name="Admin User",
        is_active=True,
        role="admin"
    )
    db.add(user)
    db.commit()
    
    jti = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    SessionService.create(db, user_id=int(user.id), jti=jti, expires_at=expires_at)
    db.commit()
    access_token = create_access_token({"sub": user.username, "uid": int(user.id), "jti": jti})
    return {"Authorization": f"Bearer {access_token}"}

@pytest.fixture
def operator_user_token(db):
    from app.models.user import User
    from app.core.security import get_password_hash, create_access_token
    from app.services.session_service import SessionService

    user = User(
        username="operatoruser",
        email="operator@example.com",
        hashed_password=get_password_hash("operatorpass"),
        full_name="Operator User",
        is_active=True,
        role="operator",
    )
    db.add(user)
    db.commit()

    jti = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=60)
    SessionService.create(db, user_id=int(user.id), jti=jti, expires_at=expires_at)
    db.commit()
    access_token = create_access_token({"sub": user.username, "uid": int(user.id), "jti": jti})
    return {"Authorization": f"Bearer {access_token}"}
