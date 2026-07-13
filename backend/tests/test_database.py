"""Tests for the engine-factory pattern (16-postgres-migration.md P2.1).

Covers: Postgres pool kwargs applied to the engine, the SQLite FK pragma
listener attached only for SQLite engines, and get_sessionmaker() raising
before init_engine() has run.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app import database
from app.config import Settings


@pytest.fixture(autouse=True)
def _reset_engine_state():
    # init_engine()/dispose_engine() mutate module-level globals; make sure
    # a test that calls init_engine() directly (bypassing the db_engine
    # fixture) can't leak an engine into a later test.
    yield
    database._engine = None
    database._sessionmaker = None


def _settings(**overrides) -> Settings:
    return Settings(require_secrets=False, **overrides)  # type: ignore[call-arg]


async def test_init_engine_applies_postgres_pool_kwargs():
    settings = _settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        db_pool_size=7,
        db_max_overflow=13,
    )
    database.init_engine(settings)

    assert database._engine is not None
    assert database._engine.pool.size() == 7
    # SQLAlchemy's QueuePool stores max_overflow on a private attribute;
    # exercised indirectly here via the public pool object it produced.
    assert database._engine.pool._max_overflow == 13

    await database.dispose_engine()


async def test_init_engine_sqlite_fk_pragma_attached():
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")
    database.init_engine(settings)

    async with database._engine.connect() as conn:
        result = await conn.exec_driver_sql("PRAGMA foreign_keys")
        (value,) = result.fetchone()
        assert value == 1

    await database.dispose_engine()


async def test_init_engine_postgres_does_not_attach_sqlite_fk_pragma():
    settings = _settings(database_url="postgresql+asyncpg://user:pass@localhost/db")
    with patch.object(database, "enable_sqlite_fk_pragma") as enable_fk:
        database.init_engine(settings)

    enable_fk.assert_not_called()
    await database.dispose_engine()


async def test_init_engine_sqlite_calls_enable_fk_pragma():
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")
    with patch.object(database, "enable_sqlite_fk_pragma") as enable_fk:
        database.init_engine(settings)

    enable_fk.assert_called_once_with(database._engine)
    await database.dispose_engine()


def test_get_sessionmaker_before_init_raises():
    with pytest.raises(RuntimeError, match="init_engine"):
        database.get_sessionmaker()


async def test_get_sessionmaker_after_init_returns_factory():
    settings = _settings(database_url="sqlite+aiosqlite:///:memory:")
    database.init_engine(settings)

    factory = database.get_sessionmaker()
    assert factory is not None

    await database.dispose_engine()
    assert database._sessionmaker is None


async def test_dispose_engine_without_init_is_a_noop():
    await database.dispose_engine()
    assert database._engine is None
