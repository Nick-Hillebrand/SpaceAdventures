from __future__ import annotations

import os
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import models  # noqa: F401 — import registers all ORM models with Base.metadata
from app.config import Settings
from app.database import Base, enable_sqlite_fk_pragma, get_db
from app.main import create_app
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient

# P2.5: DATABASE_URL drives which dialect the suite runs against — unset
# (dev parity) uses in-memory SQLite; CI additionally runs the same suite
# with DATABASE_URL=postgresql+asyncpg://… against a postgres:17 service.
# Per-test create/drop (rather than session-scoped rollback isolation) is
# kept deliberately: it is correct on both dialects without the SAVEPOINT
# sessionmaker rewrite that Postgres CI performance would otherwise call
# for — that optimization is deferred to Step P3, when the CI pipeline is
# actually stood up and can be measured against a live Postgres service
# container (see `16-postgres-migration.md` P2.5).
_TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(_TEST_DATABASE_URL, future=True)
    if not _TEST_DATABASE_URL.startswith("postgresql"):
        enable_sqlite_fk_pragma(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="",
        # Test transport is plain HTTP (ASGITransport over "http://test");
        # a Secure cookie would never round-trip through httpx's cookie jar.
        cookie_secure=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
        n2yo_api_key="TEST_N2YO",
        n2yo_base_url="https://api.n2yo.example/rest/v1/satellite",
        n2yo_hourly_cap=900,
        ll2_base_url="https://ll.thespacedevs.example",
    )


@pytest_asyncio.fixture
async def client(db_engine, settings) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app = create_app(settings=settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await app.state.nasa_client.close()
        await app.state.n2yo_client.close()
        await app.state.ll2_client.close()
        await app.state.mars_raw_images_client.close()


def pytest_collection_modifyitems(config, items):
    # 17-worker-and-scheduling.md P3.3: on SQLite, `with_for_update()` is a
    # silent no-op — these tests would only prove single-writer serialization,
    # not the Postgres row-locking they exist to verify. CI runs the full
    # suite a second time with DATABASE_URL pointed at a postgres service,
    # where they actually execute.
    if _TEST_DATABASE_URL.startswith("postgresql"):
        return
    skip_postgres_only = pytest.mark.skip(reason="requires Postgres (DATABASE_URL is SQLite)")
    for item in items:
        if "postgres_only" in item.keywords:
            item.add_marker(skip_postgres_only)
