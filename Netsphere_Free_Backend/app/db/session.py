import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


# ========================================
# Database Configuration
# ========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./netmanager.db")

# SQLAlchemy async URLs require explicit async dialects.
ASYNC_DATABASE_URL = (
    DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    .replace("sqlite:///", "sqlite+aiosqlite:///")
)


# ========================================
# Engine Configuration
# ========================================
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    pool_size = max(_env_int("DB_POOL_SIZE", 20), 1)
    max_overflow = max(_env_int("DB_MAX_OVERFLOW", 40), 0)
    pool_timeout = max(_env_int("DB_POOL_TIMEOUT_SECONDS", 30), 1)
    pool_recycle = max(_env_int("DB_POOL_RECYCLE_SECONDS", 1800), 30)

    engine = create_engine(
        DATABASE_URL,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
    )
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session
