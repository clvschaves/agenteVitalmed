"""
Sessões de banco de dados — async (FastAPI) e sync (Alembic/scripts).
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.db.models import Base  # noqa: F401 — necessário para Alembic autodiscover

# ─── Engine Async (FastAPI) ───────────────────────────────────────────────────

async_engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=(settings.app_env == "development"),
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency para FastAPI — injeta sessão async."""
    async with AsyncSessionLocal() as session:
        yield session


# ─── Engine Sync (Alembic / scripts) ────────────────────────────────────────

sync_engine = create_engine(
    settings.database_url_sync,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)
