"""SQLAlchemy engine and session factory setup."""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ibkr_mcp_service.config import get_settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""
    pass


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a cached factory that produces new AsyncSession instances.

    The engine is created once and reused across all calls to avoid
    leaking connection pools.
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
