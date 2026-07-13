from datetime import timezone as _timezone
from typing import AsyncIterator

from sqlalchemy import DateTime, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.config import Settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime(timezone=True) that reattaches UTC tzinfo on read.

    SQLite silently drops the UTC offset on read-back even for a
    timezone=True column (Postgres round-trips it correctly) — see
    `16-postgres-migration.md` P2.3. Normalizing here keeps comparisons
    and arithmetic between freshly-computed and DB-read datetimes
    consistent across both dialects. All values must still be written as
    aware UTC (`datetime.now(timezone.utc)`).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=_timezone.utc)
        return value


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def enable_sqlite_fk_pragma(engine: AsyncEngine) -> None:
    """Turn on FK enforcement for a SQLite engine.

    Attached to this engine's sync engine only, not the global
    `sqlalchemy.engine.Engine` class event — a global listener would also
    fire (harmlessly, but incorrectly) for a Postgres engine. Callers must
    only invoke this for SQLite engines (no-op guard is not needed since
    the PRAGMA is simply ignored by non-SQLite drivers, but keeping it
    dialect-conditional avoids the pointless connect-time round trip).
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, connection_record):  # pragma: no cover - engine hook
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        except Exception:  # noqa: S110 -- best-effort pragma; FK enforcement
            # already active on every real SQLite driver, so a failure here
            # has no observable effect worth logging.
            pass


def init_engine(settings: Settings) -> None:
    global _engine, _sessionmaker
    kwargs: dict = {"future": True}
    is_postgres = settings.database_url.startswith("postgresql")
    if is_postgres:
        kwargs |= {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_pre_ping": True,
        }
    _engine = create_async_engine(settings.database_url, **kwargs)

    if not is_postgres:
        enable_sqlite_fk_pragma(_engine)

    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_engine() must be called before get_sessionmaker()")
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
