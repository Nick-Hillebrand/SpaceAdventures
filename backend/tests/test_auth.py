"""Auth endpoint tests — covers all cases listed in Architecture/11-testing.md §Auth tests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import LoginAttempt, Otp, RefreshToken, User
from app.services import auth_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REGISTER_PAYLOAD = {
    "first_name": "Alice",
    "last_name": "Liddell",
    "email": "alice@example.com",
    "password": "securepassword",
}


async def _register(client) -> dict:
    """Register a user and return the response body."""
    r = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 201, r.text
    return r.json()


async def _get_otp(db_session: AsyncSession, user_id: int, channel: str) -> Otp:
    db_session.expire_all()
    result = await db_session.execute(
        select(Otp)
        .where(Otp.user_id == user_id, Otp.channel == channel)
        .order_by(Otp.id.desc())
        .limit(1)
    )
    otp = result.scalars().first()
    assert otp is not None, f"No OTP found for user {user_id} channel {channel}"
    return otp


async def _login(client, email_or_phone="alice@example.com", password="securepassword"):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": email_or_phone, "password": password},
    )
    return r


async def _auth_headers(client) -> dict:
    """Register + login and return bearer auth headers."""
    await _register(client)
    r = await _login(client)
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def test_register_success(client, db_session):
    body = await _register(client)
    user_id = body["id"]

    # User created in DB
    user = await db_session.get(User, user_id)
    assert user is not None
    assert user.email == "alice@example.com"
    assert user.password_hash != "securepassword"

    # OTP row created for email channel
    otp = await _get_otp(db_session, user_id, "email")
    assert otp is not None


async def test_register_missing_email_and_phone(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Bob", "last_name": "Smith", "password": "securepass"},
    )
    assert r.status_code == 422


async def test_register_password_too_short(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"first_name": "Bob", "last_name": "Smith", "email": "bob@x.com", "password": "short"},
    )
    assert r.status_code == 422


async def test_register_duplicate_email_generic_error(client):
    await _register(client)
    # Register again with same email
    r = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "REGISTRATION_FAILED"


async def test_register_duplicate_phone_generic_error(client):
    payload = {
        "first_name": "Alice",
        "last_name": "Liddell",
        "phone": "+15551234567",
        "password": "securepassword",
    }
    r1 = await client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 422
    body = r2.json()
    assert body["error"]["code"] == "REGISTRATION_FAILED"


# ---------------------------------------------------------------------------
# OTP verification
# ---------------------------------------------------------------------------


async def test_verify_email_otp_success(client, db_session, settings):
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])
    otp = await _get_otp(db_session, user_id, "email")

    # Retrieve plaintext code — we need the raw code; use a fresh OTP by inspecting DB
    # Since hash is bcrypt, we can't reverse it. We need to use the service directly.
    # Generate a fresh OTP via resend with a known code:
    # Instead, regenerate an OTP with a known code by patching generate_otp
    import unittest.mock as mock
    known_code = "123456"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        with mock.patch("app.services.auth_service.hash_otp", side_effect=auth_service.hash_otp):
            await auth_service.resend_otp(db_session, user_id, "email", settings)

    r = await client.post("/api/v1/auth/verify/email", json={"otp": known_code}, headers=headers)
    assert r.status_code == 200

    await db_session.refresh(await db_session.get(User, user_id))
    user = await db_session.get(User, user_id)
    assert user.email_verified is True


async def test_verify_phone_otp_success(client, db_session, settings):
    payload_reg = {
        "first_name": "Carol",
        "last_name": "Danvers",
        "phone": "+15559876543",
        "password": "securepassword",
    }
    r = await client.post("/api/v1/auth/register", json=payload_reg)
    assert r.status_code == 201
    user_id = r.json()["id"]

    # Login
    r = await client.post("/api/v1/auth/login", json={"email_or_phone": "+15559876543", "password": "securepassword"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    import unittest.mock as mock
    known_code = "654321"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user_id, "phone", settings)

    r = await client.post("/api/v1/auth/verify/phone", json={"otp": known_code}, headers=headers)
    assert r.status_code == 200

    user = await db_session.get(User, user_id)
    assert user.phone_verified is True


async def test_verify_otp_already_verified_noop(client, db_session, settings):
    """Verifying an already-verified channel returns 200 without error."""
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])

    # Mark email as verified directly
    user = await db_session.get(User, user_id)
    user.email_verified = True
    await db_session.commit()

    r = await client.post("/api/v1/auth/verify/email", json={"otp": "000000"}, headers=headers)
    assert r.status_code == 200


async def test_verify_otp_wrong_code(client, db_session, settings):
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    r = await client.post("/api/v1/auth/verify/email", json={"otp": "000000"}, headers=headers)
    assert r.status_code == 400


async def test_verify_otp_expired(client, db_session, settings):
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])

    # Set OTP expires_at to past
    otp = await _get_otp(db_session, user_id, "email")
    otp.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    r = await client.post("/api/v1/auth/verify/email", json={"otp": "000000"}, headers=headers)
    assert r.status_code == 400


async def test_verify_otp_reuse(client, db_session, settings):
    """Using the same OTP twice should fail: verify_otp returns False for used OTPs."""
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])

    import unittest.mock as mock
    known_code = "111222"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user_id, "email", settings)

    # Mark the newest OTP as used (simulating a reuse attack without going through route)
    otp = await _get_otp(db_session, user_id, "email")
    otp.used = True
    await db_session.commit()

    # Attempt to verify with the used OTP — should return False
    result = await auth_service.verify_otp(db_session, user_id, "email", known_code)
    assert result is False


async def test_verify_otp_brute_force_lockout(client, db_session, settings):
    """After 5 wrong attempts the OTP row should be deleted."""
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])

    for _ in range(5):
        r = await client.post("/api/v1/auth/verify/email", json={"otp": "000000"}, headers=headers)
        # 5th attempt deletes the OTP row

    # After lockout, another attempt returns 400 (no OTP row found)
    r = await client.post("/api/v1/auth/verify/email", json={"otp": "000000"}, headers=headers)
    assert r.status_code == 400

    # OTP row should be gone
    result = await db_session.execute(
        select(Otp).where(Otp.user_id == user_id, Otp.channel == "email", Otp.used == False)  # noqa: E712
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# OTP resend
# ---------------------------------------------------------------------------


async def test_resend_otp_success(client, db_session, settings):
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/api/v1/auth/verify/resend", json={"channel": "email"}, headers=headers)
    assert r.status_code == 200


async def test_resend_otp_rate_limit(client, db_session, settings):
    """6th resend within 1 hour should return 429."""
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = jwt_payload(token, settings)
    user_id = int(payload["sub"])

    # We already have 1 OTP from registration. Add 5 more directly via service.
    for _ in range(5):
        await auth_service.resend_otp(db_session, user_id, "email", settings)

    # 6th resend via API — should hit rate limit
    r = await client.post("/api/v1/auth/verify/resend", json={"channel": "email"}, headers=headers)
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_success(client):
    await _register(client)
    r = await _login(client)
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password(client):
    await _register(client)
    r = await _login(client, password="wrongpassword")
    assert r.status_code == 401


async def test_login_rate_limit(client, db_session):
    """6th failed login attempt should return 429 with Retry-After header."""
    await _register(client)
    for _ in range(5):
        await _login(client, password="wrongpassword")

    r = await _login(client, password="wrongpassword")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


async def test_login_clears_attempts_on_success(client, db_session, settings):
    """Successful login clears prior failed attempts."""
    await _register(client)
    for _ in range(3):
        await _login(client, password="wrongpassword")

    # Successful login
    r = await _login(client)
    assert r.status_code == 200

    # DB should have no LoginAttempt rows for this identifier
    identifier_hash = auth_service.sha256_identifier("alice@example.com")
    result = await db_session.execute(
        select(LoginAttempt).where(LoginAttempt.identifier == identifier_hash)
    )
    assert result.scalars().all() == []


async def test_login_nonexistent_user(client):
    r = await _login(client, email_or_phone="nobody@example.com")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


async def test_refresh_success(client):
    await _register(client)
    r = await _login(client)
    old_refresh = r.json()["refresh_token"]

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["refresh_token"] != old_refresh


async def test_refresh_invalid_token(client):
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "notavalidtoken"})
    assert r.status_code == 401


async def test_refresh_revoked_token(client):
    await _register(client)
    r = await _login(client)
    old_refresh = r.json()["refresh_token"]

    # Rotate — this revokes the old token
    await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

    # Attempt to use old token again
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


async def test_refresh_expired_token(client, db_session):
    await _register(client)
    r = await _login(client)
    raw_refresh = r.json()["refresh_token"]
    token_hash = auth_service.hash_refresh_token(raw_refresh)

    # Expire the token
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_row = result.scalar_one()
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout_success(client, db_session):
    await _register(client)
    r = await _login(client)
    raw_refresh = r.json()["refresh_token"]

    r = await client.post("/api/v1/auth/logout", json={"refresh_token": raw_refresh})
    assert r.status_code == 200

    # Token should be revoked
    token_hash = auth_service.hash_refresh_token(raw_refresh)
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_row = result.scalar_one()
    assert token_row.revoked is True


async def test_logout_invalid_token(client):
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": "badtoken"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Me endpoint
# ---------------------------------------------------------------------------


async def test_me_success(client, settings):
    await _register(client)
    r = await _login(client)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert "password_hash" not in body


async def test_me_expired_access_token(client, settings):
    await _register(client)
    # Create an expired token manually
    from datetime import timedelta
    from jose import jwt as jose_jwt

    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "iat": datetime.now(timezone.utc) - timedelta(seconds=901),
    }
    expired_token = jose_jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401


async def test_me_invalid_token(client):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer notavalidtoken"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Concurrent refresh (P10)
# ---------------------------------------------------------------------------


async def test_concurrent_refresh_only_one_succeeds(client):
    """Two simultaneous refresh calls with the same token — only one should succeed."""
    await _register(client)
    r = await _login(client)
    raw_refresh = r.json()["refresh_token"]

    async def do_refresh():
        return await client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})

    results = await asyncio.gather(do_refresh(), do_refresh())
    statuses = [r.status_code for r in results]

    # Exactly one should succeed and one should fail
    assert statuses.count(200) == 1
    assert statuses.count(401) == 1


# ---------------------------------------------------------------------------
# Helper: decode JWT without verification for test introspection
# ---------------------------------------------------------------------------


def jwt_payload(token: str, settings) -> dict:
    from jose import jwt as jose_jwt
    return jose_jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": False},
    )
