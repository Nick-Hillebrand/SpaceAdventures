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


async def test_verify_phone_already_verified_noop(client, db_session, settings):
    """Verifying an already-verified phone returns 200 without error."""
    payload_reg = {
        "first_name": "Dan",
        "last_name": "Miller",
        "phone": "+15550001111",
        "password": "securepassword",
    }
    r = await client.post("/api/v1/auth/register", json=payload_reg)
    user_id = r.json()["id"]
    r = await client.post("/api/v1/auth/login", json={"email_or_phone": "+15550001111", "password": "securepassword"})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    user = await db_session.get(User, user_id)
    user.phone_verified = True
    await db_session.commit()

    r = await client.post("/api/v1/auth/verify/phone", json={"otp": "000000"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Already verified"


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
    assert "refresh_token" not in body

    cookie = r.cookies.get("sa_refresh")
    assert cookie is not None
    set_cookie_header = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=strict" in set_cookie_header.lower()
    assert "path=/api/v1/auth" in set_cookie_header.lower()


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
    old_refresh = r.cookies.get("sa_refresh")

    # Cookie rides along automatically via the client's cookie jar.
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" not in body

    new_refresh = r.cookies.get("sa_refresh")
    assert new_refresh is not None
    assert new_refresh != old_refresh


async def test_refresh_via_body_fallback(client):
    """Back-compat: body-supplied refresh_token still works for one release."""
    await _register(client)
    r = await _login(client)
    old_refresh = r.cookies.get("sa_refresh")
    client.cookies.clear()

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200
    assert r.cookies.get("sa_refresh") is not None


async def test_refresh_invalid_token(client):
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": "notavalidtoken"})
    assert r.status_code == 401


async def test_refresh_no_token_at_all(client):
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


async def test_refresh_revoked_token(client):
    await _register(client)
    r = await _login(client)
    old_refresh = r.cookies.get("sa_refresh")

    # Rotate — this revokes the old token
    await client.post("/api/v1/auth/refresh")

    # Attempt to use old (now-revoked) token again explicitly via body; clear
    # the jar first since the cookie (now holding the rotated token) takes
    # precedence over the body when both are present.
    client.cookies.clear()
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


async def test_refresh_expired_token(client, db_session):
    await _register(client)
    r = await _login(client)
    raw_refresh = r.cookies.get("sa_refresh")
    token_hash = auth_service.hash_refresh_token(raw_refresh)

    # Expire the token
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_row = result.scalar_one()
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout_success(client, db_session):
    await _register(client)
    r = await _login(client)
    raw_refresh = r.cookies.get("sa_refresh")

    r = await client.post("/api/v1/auth/logout")
    assert r.status_code == 200

    # Cookie should be cleared (Max-Age=0 / expired)
    set_cookie_headers = r.headers.get_list("set-cookie")
    matches = [h for h in set_cookie_headers if h.startswith("sa_refresh=")]
    assert matches, set_cookie_headers
    assert ("max-age=0" in matches[0].lower()) or ("1970" in matches[0])

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
    import jwt as pyjwt

    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "iat": datetime.now(timezone.utc) - timedelta(seconds=901),
    }
    expired_token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401


async def test_me_invalid_token(client):
    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer notavalidtoken"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# P1.3 — PyJWT migration: reject non-conforming/forged tokens
# ---------------------------------------------------------------------------


async def test_me_token_without_exp_claim_rejected(client, settings):
    import jwt as pyjwt

    await _register(client)
    payload = {"sub": "1"}  # no exp claim
    token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_me_token_signed_with_wrong_key_rejected(client, settings):
    import jwt as pyjwt

    await _register(client)
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    token = pyjwt.encode(payload, "a-completely-different-key", algorithm=settings.jwt_algorithm)

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


async def test_me_token_alg_none_rejected(client):
    import jwt as pyjwt

    await _register(client)
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
    }
    # PyJWT refuses to even encode with alg "none" unless the key is None;
    # construct the classic unsigned "alg: none" token by hand instead.
    import base64
    import json

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload, default=str).encode())
    forged_token = f"{header}.{body}."

    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Concurrent refresh (P10)
# ---------------------------------------------------------------------------


@pytest.mark.postgres_only
async def test_concurrent_refresh_only_one_succeeds(client):
    """Two simultaneous refresh calls with the same token — only one should succeed.

    Requires Postgres row locking (`FOR UPDATE` is a no-op on SQLite) —
    17-worker-and-scheduling.md P3.3."""
    await _register(client)
    r = await _login(client)
    raw_refresh = r.cookies.get("sa_refresh")

    async def do_refresh():
        return await client.post("/api/v1/auth/refresh", json={"refresh_token": raw_refresh})

    results = await asyncio.gather(do_refresh(), do_refresh())
    statuses = [r.status_code for r in results]

    # Exactly one should succeed and one should fail
    assert statuses.count(200) == 1
    assert statuses.count(401) == 1


@pytest.mark.postgres_only
async def test_concurrent_otp_resend_at_limit(db_session, settings):
    """Two simultaneous resends at the rate-limit boundary — only one should
    succeed, the other must see OTP_RATE_LIMIT.

    Requires Postgres row locking (`FOR UPDATE` is a no-op on SQLite) —
    17-worker-and-scheduling.md P3.3."""
    user = await auth_service.register_user(
        db_session,
        {
            "first_name": "Otp",
            "last_name": "Race",
            "email": "otp_race@example.com",
            "password": "testpassword",
        },
        settings,
    )
    # Registration creates 1 OTP; 4 more sequential resends bring the count to
    # 5 (== _MAX_OTP_RESENDS) — right at the boundary where the next resend
    # must be rejected.
    for _ in range(4):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    async def attempt():
        try:
            await auth_service.resend_otp(db_session, user.id, "email", settings)
            return "ok"
        except ValueError as exc:
            return str(exc)

    results = await asyncio.gather(attempt(), attempt())

    assert results.count("ok") == 1
    assert results.count("OTP_RATE_LIMIT") == 1


# ---------------------------------------------------------------------------
# Consent recording (P1.9)
# ---------------------------------------------------------------------------


async def test_register_without_consent_leaves_it_null(client, db_session):
    body = await _register(client)
    user = await db_session.get(User, body["id"])
    assert user.consent_notifications_at is None
    assert user.consent_source is None


async def test_register_with_consent_records_timestamp_and_source(client, db_session):
    payload = {**REGISTER_PAYLOAD, "email": "consent@example.com", "consent_notifications": True}
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    user = await db_session.get(User, r.json()["id"])
    assert user.consent_notifications_at is not None
    assert user.consent_source == "register-form-v1"


async def test_consent_endpoint_grant_and_withdraw(client):
    headers = await _auth_headers(client)

    r = await client.post("/api/v1/auth/consent", json={"granted": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["consent_notifications_at"] is not None

    r2 = await client.post("/api/v1/auth/consent", json={"granted": False}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["consent_notifications_at"] is None


async def test_consent_endpoint_unauthenticated(client):
    r = await client.post("/api/v1/auth/consent", json={"granted": True})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Account deletion & data export (P1.10)
# ---------------------------------------------------------------------------


async def test_delete_account_wrong_password_returns_403_no_deletion(client, db_session):
    headers = await _auth_headers(client)

    r = await client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "wrongpassword"}, headers=headers
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "INVALID_PASSWORD"

    db_session.expire_all()
    result = await db_session.execute(select(User).where(User.email == "alice@example.com"))
    assert result.scalar_one_or_none() is not None


async def test_delete_account_unauthenticated(client):
    r = await client.request("DELETE", "/api/v1/auth/me", json={"password": "whatever"})
    assert r.status_code == 401


async def test_delete_account_success_cascades_and_clears_cookie(client, db_session):
    from app.models.notification_log import NotificationLog
    from app.models.subscription import Subscription

    await _register(client)
    login_r = await _login(client)
    old_refresh = login_r.cookies.get("sa_refresh")
    token = login_r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    user_id = me.json()["id"]

    # Grant consent and create a subscription to exercise its cascade.
    await client.post("/api/v1/auth/consent", json={"granted": True}, headers=headers)
    sub_r = await client.post(
        "/api/v1/subscriptions",
        json={"type": "agency", "agency_name": "SpaceX", "notify_email": True, "notify_sms": False},
        headers=headers,
    )
    assert sub_r.status_code == 201, sub_r.text

    # A notification_log row referencing this user (billing/audit record).
    db_session.add(
        NotificationLog(
            user_id=user_id,
            ll2_id="launch-1",
            change_type="STATUS_CHANGE",
            channel="email",
            delivery_status="sent",
        )
    )
    await db_session.commit()

    r = await client.request(
        "DELETE", "/api/v1/auth/me", json={"password": "securepassword"}, headers=headers
    )
    assert r.status_code == 204

    set_cookie_headers = r.headers.get_list("set-cookie")
    matches = [h for h in set_cookie_headers if h.startswith("sa_refresh=")]
    assert matches
    assert ("max-age=0" in matches[0].lower()) or ("1970" in matches[0])

    db_session.expire_all()

    assert await db_session.get(User, user_id) is None

    otp_result = await db_session.execute(select(Otp).where(Otp.user_id == user_id))
    assert otp_result.scalars().all() == []

    rt_result = await db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
    assert rt_result.scalars().all() == []

    sub_result = await db_session.execute(select(Subscription).where(Subscription.user_id == user_id))
    assert sub_result.scalars().all() == []

    # notification_log row survives, anonymized (user_id -> NULL), not deleted.
    log_result = await db_session.execute(
        select(NotificationLog).where(NotificationLog.ll2_id == "launch-1")
    )
    log_rows = log_result.scalars().all()
    assert len(log_rows) == 1
    assert log_rows[0].user_id is None

    # The deleted user's refresh cookie can no longer mint access tokens.
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401


async def test_export_account_contains_no_sensitive_fields(client):
    headers = await _auth_headers(client)
    await client.post("/api/v1/auth/consent", json={"granted": True}, headers=headers)
    await client.post(
        "/api/v1/subscriptions",
        json={"type": "agency", "agency_name": "SpaceX", "notify_email": True, "notify_sms": False},
        headers=headers,
    )

    r = await client.get("/api/v1/auth/me/export", headers=headers)
    assert r.status_code == 200
    body = r.json()

    assert body["profile"]["email"] == "alice@example.com"
    assert "password_hash" not in body["profile"]
    assert len(body["subscriptions"]) == 1
    assert body["subscriptions"][0]["agency_name"] == "SpaceX"
    assert body["notification_history"] == []

    body_str = str(body)
    assert "password" not in body_str.lower()
    assert "token_hash" not in body_str.lower()


async def test_export_account_unauthenticated(client):
    r = await client.get("/api/v1/auth/me/export")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Helper: decode JWT without verification for test introspection
# ---------------------------------------------------------------------------


def jwt_payload(token: str, settings) -> dict:
    import jwt as pyjwt
    return pyjwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": False},
    )


# ---------------------------------------------------------------------------
# Direct service-level unit tests (bypass HTTP stack for reliable coverage)
# ---------------------------------------------------------------------------


async def _make_svc_user(session: AsyncSession, email: str) -> User:
    user = User(
        first_name="Svc",
        last_name="Test",
        email=email,
        password_hash=auth_service.hash_password("testpass"),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_service_register_otp_created(db_session, settings):
    data = {"first_name": "Svc", "last_name": "Test", "email": "svc_reg@example.com", "password": "testpass"}
    user = await auth_service.register_user(db_session, data, settings)
    assert user.id is not None
    otp = await _get_otp(db_session, user.id, "email")
    assert otp is not None


async def test_service_register_phone_creates_otp(db_session, settings):
    data = {"first_name": "Svc", "last_name": "Test", "phone": "+15551234567", "password": "testpass"}
    user = await auth_service.register_user(db_session, data, settings)
    assert user.id is not None
    otp = await _get_otp(db_session, user.id, "phone")
    assert otp is not None


async def test_service_register_duplicate_raises(db_session, settings):
    data = {"first_name": "Svc", "last_name": "Test", "email": "svc_dup@example.com", "password": "testpass"}
    await auth_service.register_user(db_session, data, settings)
    with pytest.raises(ValueError, match="REGISTRATION_FAILED"):
        await auth_service.register_user(db_session, data, settings)


async def test_service_set_consent_grant_then_withdraw(db_session):
    user = await _make_svc_user(db_session, "svc_consent@example.com")
    assert user.consent_notifications_at is None

    granted = await auth_service.set_consent(db_session, user, True)
    assert granted.consent_notifications_at is not None
    assert granted.consent_source == "account-settings-v1"

    withdrawn = await auth_service.set_consent(db_session, user, False)
    assert withdrawn.consent_notifications_at is None
    assert withdrawn.consent_source is None


async def test_service_delete_account_wrong_password_raises(db_session):
    user = await _make_svc_user(db_session, "svc_del_wrong@example.com")
    with pytest.raises(ValueError, match="INVALID_PASSWORD"):
        await auth_service.delete_account(db_session, user, "not-the-password")

    still_there = await db_session.get(User, user.id)
    assert still_there is not None


async def test_service_verify_otp_not_found_returns_false(db_session, settings):
    user = await _make_svc_user(db_session, "svc_votp_nf@example.com")
    result = await auth_service.verify_otp(db_session, user.id, "email", "123456")
    assert result is False


async def test_service_verify_otp_expired_returns_false(db_session, settings):
    import unittest.mock as mock
    user = await _make_svc_user(db_session, "svc_votp_exp@example.com")
    known_code = "111111"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    otp_result = await db_session.execute(
        select(Otp).where(Otp.user_id == user.id, Otp.channel == "email", Otp.used == False)  # noqa: E712
    )
    for otp in otp_result.scalars().all():
        otp.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.commit()

    result = await auth_service.verify_otp(db_session, user.id, "email", known_code)
    assert result is False


async def test_service_verify_otp_wrong_code_increments_failures(db_session, settings):
    import unittest.mock as mock
    user = await _make_svc_user(db_session, "svc_votp_wrong@example.com")
    known_code = "222222"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    result = await auth_service.verify_otp(db_session, user.id, "email", "999999")
    assert result is False
    otp = await _get_otp(db_session, user.id, "email")
    assert otp.failed_attempts == 1


async def test_service_verify_otp_max_failures_deletes_row(db_session, settings):
    import unittest.mock as mock
    user = await _make_svc_user(db_session, "svc_votp_max@example.com")
    known_code = "333333"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    for _ in range(5):
        await auth_service.verify_otp(db_session, user.id, "email", "999999")

    otp_result = await db_session.execute(
        select(Otp).where(Otp.user_id == user.id, Otp.channel == "email", Otp.used == False)  # noqa: E712
    )
    assert otp_result.scalar_one_or_none() is None


async def test_service_verify_otp_success_sets_verified(db_session, settings):
    import unittest.mock as mock
    user = await _make_svc_user(db_session, "svc_votp_ok@example.com")
    known_code = "444444"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    result = await auth_service.verify_otp(db_session, user.id, "email", known_code)
    assert result is True
    refreshed = await db_session.get(User, user.id)
    assert refreshed.email_verified is True


async def test_service_verify_otp_phone_success_sets_verified(db_session, settings):
    import unittest.mock as mock
    data = {"first_name": "Svc", "last_name": "Test", "phone": "+15551234568", "password": "testpass"}
    user = await auth_service.register_user(db_session, data, settings)
    known_code = "555555"
    with mock.patch("app.services.auth_service.generate_otp", return_value=known_code):
        await auth_service.resend_otp(db_session, user.id, "phone", settings)
    result = await auth_service.verify_otp(db_session, user.id, "phone", known_code)
    assert result is True
    refreshed = await db_session.get(User, user.id)
    assert refreshed.phone_verified is True


async def test_service_resend_otp_rate_limit(db_session, settings):
    user = await _make_svc_user(db_session, "svc_resend_rl@example.com")
    for _ in range(6):
        await auth_service.resend_otp(db_session, user.id, "email", settings)
    with pytest.raises(ValueError, match="OTP_RATE_LIMIT"):
        await auth_service.resend_otp(db_session, user.id, "email", settings)


async def test_service_login_rate_limit(db_session, settings):
    await _make_svc_user(db_session, "svc_login_rl@example.com")
    for _ in range(5):
        with pytest.raises(ValueError):
            await auth_service.login(db_session, "svc_login_rl@example.com", "wrongpass", "127.0.0.1", settings)
    with pytest.raises(ValueError, match="RATE_LIMITED"):
        await auth_service.login(db_session, "svc_login_rl@example.com", "testpass", "127.0.0.1", settings)


async def test_service_login_wrong_password(db_session, settings):
    await _make_svc_user(db_session, "svc_login_wp@example.com")
    with pytest.raises(ValueError, match="LOGIN_FAILED"):
        await auth_service.login(db_session, "svc_login_wp@example.com", "wrongpass", "127.0.0.1", settings)


async def test_service_login_user_not_found(db_session, settings):
    with pytest.raises(ValueError, match="LOGIN_FAILED"):
        await auth_service.login(db_session, "nobody_svc@example.com", "pass", "127.0.0.1", settings)


async def test_service_login_success_and_clears_attempts(db_session, settings):
    await _make_svc_user(db_session, "svc_login_ok@example.com")
    with pytest.raises(ValueError):
        await auth_service.login(db_session, "svc_login_ok@example.com", "wrongpass", "127.0.0.1", settings)
    access, refresh = await auth_service.login(db_session, "svc_login_ok@example.com", "testpass", "127.0.0.1", settings)
    assert access
    assert refresh
    identifier_hash = auth_service.sha256_identifier("svc_login_ok@example.com")
    result = await db_session.execute(
        select(LoginAttempt).where(LoginAttempt.identifier == identifier_hash)
    )
    assert result.scalars().all() == []


async def test_service_refresh_not_found(db_session, settings):
    with pytest.raises(ValueError, match="INVALID_REFRESH_TOKEN"):
        await auth_service.refresh_tokens(db_session, "nonexistenttoken", settings)


async def test_service_refresh_revoked(db_session, settings):
    await _make_svc_user(db_session, "svc_refresh_rev@example.com")
    _, raw_refresh = await auth_service.login(db_session, "svc_refresh_rev@example.com", "testpass", "127.0.0.1", settings)
    await auth_service.refresh_tokens(db_session, raw_refresh, settings)
    with pytest.raises(ValueError, match="REVOKED_REFRESH_TOKEN"):
        await auth_service.refresh_tokens(db_session, raw_refresh, settings)


async def test_service_refresh_expired(db_session, settings):
    await _make_svc_user(db_session, "svc_refresh_exp@example.com")
    _, raw_refresh = await auth_service.login(db_session, "svc_refresh_exp@example.com", "testpass", "127.0.0.1", settings)
    token_hash = auth_service.hash_refresh_token(raw_refresh)

    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_row = result.scalar_one()
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    with pytest.raises(ValueError, match="EXPIRED_REFRESH_TOKEN"):
        await auth_service.refresh_tokens(db_session, raw_refresh, settings)


async def test_service_refresh_success(db_session, settings):
    await _make_svc_user(db_session, "svc_refresh_ok@example.com")
    _, raw_refresh = await auth_service.login(db_session, "svc_refresh_ok@example.com", "testpass", "127.0.0.1", settings)
    new_access, new_refresh = await auth_service.refresh_tokens(db_session, raw_refresh, settings)
    assert new_access
    assert new_refresh != raw_refresh


async def test_service_logout_not_found(db_session, settings):
    with pytest.raises(ValueError, match="INVALID_REFRESH_TOKEN"):
        await auth_service.logout(db_session, "nonexistenttoken")


async def test_service_get_current_user_invalid_sub(db_session, settings):
    import jwt as pyjwt
    payload = {"exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(ValueError, match="INVALID_TOKEN"):
        await auth_service.get_current_user(db_session, token, settings)


async def test_service_get_current_user_non_integer_sub(db_session, settings):
    import jwt as pyjwt
    payload = {"sub": "not-a-number", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    token = pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(ValueError, match="INVALID_TOKEN"):
        await auth_service.get_current_user(db_session, token, settings)


async def test_service_get_current_user_not_found(db_session, settings):
    token = auth_service.create_access_token(99999, settings)
    with pytest.raises(ValueError, match="USER_NOT_FOUND"):
        await auth_service.get_current_user(db_session, token, settings)
