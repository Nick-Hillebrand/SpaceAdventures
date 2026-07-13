from __future__ import annotations

from typing import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import models  # noqa: F401 — import registers all ORM models with Base.metadata
from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
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
