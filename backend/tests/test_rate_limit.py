"""IP-level rate limiting tests (P1.6) — see Architecture/15-production-hardening.md."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.main import create_app
from app.models.rate_limit import RateLimitEvent
from app.rate_limit import (
    AUTH_LIMIT,
    OTP_SEND_BUCKET,
    OTP_SEND_LIMIT,
    _check_and_record,
    hash_ip,
    rate_limiter,
)
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient

REGISTER_PAYLOAD = {
    "first_name": "Alice",
    "last_name": "Liddell",
    "email": "alice@example.com",
    "password": "securepassword",
}


async def _register(client) -> dict:
    r = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    return r.json()


async def _login(client, email_or_phone="alice@example.com", password="securepassword", **kwargs):
    return await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": email_or_phone, "password": password},
        **kwargs,
    )


async def _make_client(db_engine, settings) -> AsyncClient:
    """Mirror conftest.py's `client` fixture but let the caller vary `settings`."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app = create_app(settings=settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Unit tests — app.rate_limit internals
# ---------------------------------------------------------------------------


def test_hash_ip_deterministic_and_distinct():
    assert hash_ip("1.2.3.4") == hash_ip("1.2.3.4")
    assert hash_ip("1.2.3.4") != hash_ip("5.6.7.8")
    # Never store the raw IP — the hash must not just be the IP itself.
    assert hash_ip("1.2.3.4") != "1.2.3.4"


async def test_check_and_record_allows_up_to_limit_then_blocks(db_session):
    bucket, ip_hash = "test-bucket", hash_ip("9.9.9.9")
    for _ in range(3):
        exceeded = await _check_and_record(db_session, bucket, ip_hash, limit=3, window_seconds=900)
        assert exceeded is False
    exceeded = await _check_and_record(db_session, bucket, ip_hash, limit=3, window_seconds=900)
    assert exceeded is True


async def test_check_and_record_different_ips_dont_interfere(db_session):
    bucket = "test-bucket"
    ip_a, ip_b = hash_ip("1.1.1.1"), hash_ip("2.2.2.2")
    for _ in range(3):
        assert await _check_and_record(db_session, bucket, ip_a, limit=3, window_seconds=900) is False
    # ip_a is now exhausted; ip_b is untouched and independent.
    assert await _check_and_record(db_session, bucket, ip_a, limit=3, window_seconds=900) is True
    assert await _check_and_record(db_session, bucket, ip_b, limit=3, window_seconds=900) is False


async def test_dependency_raises_429_when_exceeded(db_session, settings):
    """Direct call to the `rate_limiter()`-returned dependency (bypassing the
    full ASGI stack) so the raise path is exercised in isolation."""
    dependency = rate_limiter("direct-test-bucket", limit=1, window_seconds=900)
    ip_hash = hash_ip("5.5.5.5")
    db_session.add(RateLimitEvent(bucket="direct-test-bucket", ip_hash=ip_hash))
    await db_session.commit()

    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={},
        client=SimpleNamespace(host="5.5.5.5"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await dependency(fake_request, db_session)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"]["code"] == "RATE_LIMITED"
    assert exc_info.value.headers["Retry-After"] == "900"


async def test_check_and_record_window_slides(db_session):
    bucket, ip_hash = "test-bucket", hash_ip("3.3.3.3")
    old_event = RateLimitEvent(
        bucket=bucket,
        ip_hash=ip_hash,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    db_session.add(old_event)
    await db_session.commit()

    # A 60s window has already slid past the 120s-old row, so it doesn't count.
    exceeded = await _check_and_record(db_session, bucket, ip_hash, limit=1, window_seconds=60)
    assert exceeded is False

    # A 300s window still sees it, so this second event trips a limit of 1.
    exceeded = await _check_and_record(db_session, bucket, ip_hash, limit=1, window_seconds=300)
    assert exceeded is True


# ---------------------------------------------------------------------------
# HTTP-level tests — auth bucket
# ---------------------------------------------------------------------------


async def test_31st_auth_call_within_window_is_rate_limited(client):
    await _register(client)
    r = await _login(client)
    assert r.status_code == 200, r.text

    # login = 1 auth-bucket event; 29 more successful refreshes bring the
    # total to AUTH_LIMIT (30). The refresh cookie rotates and rides the
    # client's cookie jar automatically each call.
    for _ in range(AUTH_LIMIT - 2):
        r = await client.post("/api/v1/auth/refresh")
        assert r.status_code == 200, r.text

    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in r.headers


async def test_x_forwarded_for_ignored_when_trust_proxy_headers_off(db_engine, settings):
    assert settings.trust_proxy_headers is False
    client = await _make_client(db_engine, settings)
    try:
        await _register(client)
        for i in range(AUTH_LIMIT - 1):
            r = await _login(client, headers={"X-Forwarded-For": f"10.0.0.{i}"})
            assert r.status_code in (200, 401)
        # Real transport IP is shared across all calls regardless of the
        # spoofed header, so the bucket is exhausted despite each call
        # claiming a different forwarded IP.
        r = await _login(client, headers={"X-Forwarded-For": "10.0.0.250"})
        assert r.status_code == 429
    finally:
        await client.aclose()


async def test_x_forwarded_for_honored_when_trust_proxy_headers_on(db_engine, settings):
    settings.trust_proxy_headers = True
    client = await _make_client(db_engine, settings)
    try:
        # Registration carries no X-Forwarded-For header, so it lands in the
        # real-transport-IP bucket, not the "10.0.0.1" bucket exercised below.
        await _register(client)
        for _ in range(AUTH_LIMIT):
            r = await _login(client, headers={"X-Forwarded-For": "10.0.0.1"})
            assert r.status_code in (200, 401)
        # 10.0.0.1's bucket is now exhausted.
        r = await _login(client, headers={"X-Forwarded-For": "10.0.0.1"})
        assert r.status_code == 429

        # A different forwarded IP gets its own, untouched bucket.
        r = await _login(client, headers={"X-Forwarded-For": "10.0.0.2"})
        assert r.status_code in (200, 401)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# HTTP-level tests — otp_send bucket
# ---------------------------------------------------------------------------


async def test_otp_send_bucket_blocks_before_account_level_limit(client, db_session):
    """The otp_send bucket is IP-scoped, so it must catch abuse spread across
    many accounts from one IP — simulated here by pre-seeding the bucket to
    its limit and confirming the very next call is rejected with the
    IP-level RATE_LIMITED code, not the account-level OTP_RATE_LIMIT code
    (which only trips after 6 calls for a single account)."""
    headers = await _register_and_get_auth_headers(client)

    ip_hash = hash_ip("127.0.0.1")  # httpx ASGITransport's default client address
    for _ in range(OTP_SEND_LIMIT):
        db_session.add(RateLimitEvent(bucket=OTP_SEND_BUCKET, ip_hash=ip_hash))
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/verify/resend", json={"channel": "email"}, headers=headers
    )
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "RATE_LIMITED"


async def _register_and_get_auth_headers(client) -> dict:
    await _register(client)
    r = await _login(client)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
