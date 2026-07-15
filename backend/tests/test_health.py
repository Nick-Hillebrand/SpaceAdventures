"""Tests for GET /api/v1/health — tiered public/admin response
(17-worker-and-scheduling.md P3.5, 10-security.md Health Endpoint Tiers)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport
from httpx import AsyncClient as httpxAsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.models.job_status import JobStatus
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient


@pytest_asyncio.fixture
async def admin_client(db_engine):
    """HTTP client with admin_api_key configured, for the admin health tier."""
    admin_settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key="test-admin-secret",
        ll2_base_url="https://ll.thespacedevs.example",
        n2yo_api_key="",
        smtp_host="",
    )
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    admin_app = create_app(settings=admin_settings)
    admin_app.state.nasa_client = NasaClient(admin_settings)
    admin_app.state.n2yo_client = N2YOClient(admin_settings)
    admin_app.state.ll2_client = LL2Client(admin_settings)
    admin_app.state.mars_raw_images_client = MarsRawImagesClient(admin_settings)
    admin_app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=admin_app)
    try:
        async with httpxAsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await admin_app.state.nasa_client.close()
        await admin_app.state.n2yo_client.close()
        await admin_app.state.ll2_client.close()
        await admin_app.state.mars_raw_images_client.close()


async def test_health_public_degraded_with_no_heartbeat(client):
    """No worker has ever run (fresh DB, no job_status rows) → degraded."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded"}


async def test_health_public_ok_with_fresh_heartbeat(client, db_session):
    db_session.add(
        JobStatus(job_name="worker_heartbeat", last_success_at=datetime.now(timezone.utc))
    )
    await db_session.commit()

    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_public_degraded_with_stale_heartbeat(client, db_session):
    stale = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.add(JobStatus(job_name="worker_heartbeat", last_success_at=stale))
    await db_session.commit()

    response = await client.get("/api/v1/health")
    assert response.json() == {"status": "degraded"}


async def test_health_public_no_internal_details_leaked(client):
    """Unauthenticated response is exactly {status} — no db/smtp/n2yo_quota keys."""
    response = await client.get("/api/v1/health")
    assert set(response.json().keys()) == {"status"}


async def test_health_admin_tier_wrong_key_falls_back_to_public(admin_client):
    """Wrong/missing credentials silently fall back to the public tier — the
    health route always returns 200 (external uptime monitors watch it)."""
    response = await admin_client.get(
        "/api/v1/health", headers={"Authorization": "Bearer wrong-key"}
    )
    assert response.status_code == 200
    assert set(response.json().keys()) == {"status"}


async def test_health_admin_tier_full_response(admin_client):
    response = await admin_client.get(
        "/api/v1/health", headers={"Authorization": "Bearer test-admin-secret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "ok"
    assert body["smtp"] == "unconfigured"
    assert body["n2yo_quota"] == {"status": "unconfigured"}
    assert body["jobs"]["worker_heartbeat"] == "stale"
    assert set(body["jobs"].keys()) == {
        "launches_sync", "notification_drain", "rate_limit_purge", "worker_heartbeat",
        "ephemeris_sync", "pass_precompute", "pass_notify",
    }


async def test_health_admin_status_values_never_raw_errors(admin_client):
    """Status vocabulary is restricted to the documented enum (10-security.md) —
    never a raw error message or hostname."""
    response = await admin_client.get(
        "/api/v1/health", headers={"Authorization": "Bearer test-admin-secret"}
    )
    body = response.json()
    assert body["db"] in ("ok", "error")
    assert body["smtp"] in ("ok", "unconfigured")
    assert body["n2yo_quota"]["status"] in ("ok", "unconfigured", "warning", "exhausted")
    assert all(v in ("ok", "stale") for v in body["jobs"].values())
