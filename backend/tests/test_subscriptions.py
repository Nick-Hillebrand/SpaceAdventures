"""Tests for subscription CRUD and unsubscribe-by-token endpoints."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.user import User
from app.services import auth_service
from app.services.notification_service import create_unsubscribe_token


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REGISTER_PAYLOAD = {
    "first_name": "Alice",
    "last_name": "Liddell",
    "email": "alice@example.com",
    "password": "securepassword",
    "consent_notifications": True,
}

REGISTER_PAYLOAD_BOB = {
    "first_name": "Bob",
    "last_name": "Builder",
    "email": "bob@example.com",
    "password": "securepassword2",
    "consent_notifications": True,
}


async def _register_and_login(client, payload=REGISTER_PAYLOAD) -> tuple[int, dict]:
    """Register a user and return (user_id, auth_headers)."""
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": payload["email"], "password": payload["password"]},
    )
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


async def _create_sub(client, headers: dict, body: dict):
    return await client.post("/api/v1/subscriptions", json=body, headers=headers)


# ---------------------------------------------------------------------------
# List subscriptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_subscriptions_empty(client):
    _, headers = await _register_and_login(client)
    r = await client.get("/api/v1/subscriptions", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_subscriptions_unauthenticated(client):
    r = await client.get("/api/v1/subscriptions")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Create subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_launch_subscription(client, db_session):
    _, headers = await _register_and_login(client)
    body = {
        "type": "launch",
        "ll2_id": "abc-123",
        "notify_email": True,
        "notify_sms": False,
    }
    r = await _create_sub(client, headers, body)
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "launch"
    assert data["ll2_id"] == "abc-123"
    assert data["notify_email"] is True
    assert data["notify_sms"] is False
    assert "id" in data

    # Verify in DB
    result = await db_session.execute(
        select(Subscription).where(Subscription.ll2_id == "abc-123")
    )
    sub = result.scalar_one_or_none()
    assert sub is not None


@pytest.mark.asyncio
async def test_create_agency_subscription(client, db_session):
    _, headers = await _register_and_login(client)
    body = {
        "type": "agency",
        "agency_name": "SpaceX",
        "notify_email": False,
        "notify_sms": True,
    }
    r = await _create_sub(client, headers, body)
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "agency"
    assert data["agency_name"] == "SpaceX"
    assert data["notify_sms"] is True


@pytest.mark.asyncio
async def test_create_subscription_unauthenticated(client):
    body = {"type": "launch", "ll2_id": "xyz-999", "notify_email": True, "notify_sms": False}
    r = await client.post("/api/v1/subscriptions", json=body)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# P1.9 — consent gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_subscription_without_consent_is_403(client):
    payload = {**REGISTER_PAYLOAD, "consent_notifications": False}
    _, headers = await _register_and_login(client, payload)
    body = {"type": "launch", "ll2_id": "consent-001", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, headers, body)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_grant_consent_then_subscribe_succeeds(client):
    payload = {**REGISTER_PAYLOAD, "consent_notifications": False}
    _, headers = await _register_and_login(client, payload)
    body = {"type": "launch", "ll2_id": "consent-002", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, headers, body)
    assert r.status_code == 403

    r2 = await client.post("/api/v1/auth/consent", json={"granted": True}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["consent_notifications_at"] is not None

    r3 = await _create_sub(client, headers, body)
    assert r3.status_code == 201


@pytest.mark.asyncio
async def test_withdraw_consent_blocks_new_subscriptions_but_keeps_account(client):
    _, headers = await _register_and_login(client)
    body = {"type": "launch", "ll2_id": "consent-003", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, headers, body)
    assert r.status_code == 201

    r2 = await client.post("/api/v1/auth/consent", json={"granted": False}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["consent_notifications_at"] is None

    # Account still intact — /me still works, prior subscription untouched.
    r3 = await client.get("/api/v1/auth/me", headers=headers)
    assert r3.status_code == 200

    body2 = {"type": "agency", "agency_name": "SpaceX", "notify_email": True, "notify_sms": False}
    r4 = await _create_sub(client, headers, body2)
    assert r4.status_code == 403
    assert r4.json()["detail"]["error"]["code"] == "CONSENT_REQUIRED"


# ---------------------------------------------------------------------------
# Delete subscription
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_subscription(client, db_session):
    _, headers = await _register_and_login(client)
    # Create a subscription first
    body = {"type": "launch", "ll2_id": "del-001", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, headers, body)
    assert r.status_code == 201
    sub_id = r.json()["id"]

    # Delete it
    r2 = await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=headers)
    assert r2.status_code == 204

    # Verify removed from DB
    result = await db_session.execute(
        select(Subscription).where(Subscription.id == sub_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_subscription_wrong_user(client):
    # Alice creates a subscription
    _, alice_headers = await _register_and_login(client, REGISTER_PAYLOAD)
    body = {"type": "launch", "ll2_id": "del-002", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, alice_headers, body)
    sub_id = r.json()["id"]

    # Bob tries to delete Alice's subscription
    _, bob_headers = await _register_and_login(client, REGISTER_PAYLOAD_BOB)
    r2 = await client.delete(f"/api/v1/subscriptions/{sub_id}", headers=bob_headers)
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_delete_subscription_not_found(client):
    _, headers = await _register_and_login(client)
    r = await client.delete("/api/v1/subscriptions/nonexistent-id-xyz", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_subscription_unauthenticated(client):
    r = await client.delete("/api/v1/subscriptions/some-id")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Unsubscribe by token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsubscribe_by_token_success(client, db_session, settings):
    user_id, headers = await _register_and_login(client)
    body = {"type": "launch", "ll2_id": "unsub-001", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, headers, body)
    sub_id = r.json()["id"]

    token = create_unsubscribe_token(sub_id, user_id, settings)
    r2 = await client.post("/api/v1/subscriptions/unsubscribe", json={"token": token})
    assert r2.status_code == 200
    assert "Unsubscribed" in r2.json()["message"]

    # Verify removed from DB
    db_session.expire_all()
    result = await db_session.execute(
        select(Subscription).where(Subscription.id == sub_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unsubscribe_by_token_invalid(client):
    r = await client.post(
        "/api/v1/subscriptions/unsubscribe", json={"token": "not-a-valid-jwt"}
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unsubscribe_by_token_wrong_user(client, settings):
    # Alice creates a subscription
    alice_id, alice_headers = await _register_and_login(client, REGISTER_PAYLOAD)
    body = {"type": "launch", "ll2_id": "unsub-002", "notify_email": True, "notify_sms": False}
    r = await _create_sub(client, alice_headers, body)
    sub_id = r.json()["id"]

    # Bob registers
    bob_id, _ = await _register_and_login(client, REGISTER_PAYLOAD_BOB)

    # Token with Bob's user_id but Alice's subscription_id
    token = create_unsubscribe_token(sub_id, bob_id, settings)
    r2 = await client.post("/api/v1/subscriptions/unsubscribe", json={"token": token})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_unsubscribe_by_token_expired(client, settings):
    from datetime import datetime, timedelta, timezone
    import jwt

    # Manually create an expired token
    payload = {
        "subscription_id": "some-sub-id",
        "user_id": 999,
        "exp": datetime.now(timezone.utc) - timedelta(days=1),
    }
    expired_token = jwt.encode(payload, settings.unsubscribe_secret_key, algorithm="HS256")
    r = await client.post(
        "/api/v1/subscriptions/unsubscribe", json={"token": expired_token}
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Direct service-level unit tests (bypass HTTP stack for reliable coverage)
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession, email: str, *, consent: bool = True) -> User:
    from datetime import datetime, timezone

    user = User(
        first_name="Svc",
        last_name="Test",
        email=email,
        password_hash=auth_service.hash_password("pass"),
    )
    if consent:
        user.consent_notifications_at = datetime.now(timezone.utc)
        user.consent_source = "test-fixture"
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_service_get_subscriptions_empty(db_session):
    from app.services.subscription_service import get_subscriptions

    user = await _make_user(db_session, "svc_empty@example.com")
    result = await get_subscriptions(db_session, user.id)
    assert result == []


@pytest.mark.asyncio
async def test_service_create_and_get_subscription(db_session):
    from app.services.subscription_service import create_subscription, get_subscriptions
    from app.schemas.subscription import CreateSubscriptionRequest

    user = await _make_user(db_session, "svc_create@example.com")
    req = CreateSubscriptionRequest(type="launch", ll2_id="svc-001", notify_email=True, notify_sms=False)
    sub = await create_subscription(db_session, user, req)
    assert sub.id is not None
    assert sub.ll2_id == "svc-001"

    subs = await get_subscriptions(db_session, user.id)
    assert len(subs) == 1
    assert subs[0].id == sub.id


@pytest.mark.asyncio
async def test_service_delete_subscription_not_found(db_session):
    from fastapi import HTTPException
    from app.services.subscription_service import delete_subscription

    with pytest.raises(HTTPException) as exc_info:
        await delete_subscription(db_session, "nonexistent-id", 999)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_service_delete_subscription_success(db_session):
    from app.services.subscription_service import create_subscription, delete_subscription
    from app.schemas.subscription import CreateSubscriptionRequest

    user = await _make_user(db_session, "svc_del@example.com")
    req = CreateSubscriptionRequest(type="agency", agency_name="NASA", notify_email=False, notify_sms=True)
    sub = await create_subscription(db_session, user, req)
    await delete_subscription(db_session, sub.id, user.id)

    result = await db_session.execute(select(Subscription).where(Subscription.id == sub.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_service_unsubscribe_by_token_success(db_session, settings):
    from app.services.subscription_service import create_subscription, unsubscribe_by_token
    from app.schemas.subscription import CreateSubscriptionRequest

    user = await _make_user(db_session, "svc_unsub@example.com")
    req = CreateSubscriptionRequest(type="launch", ll2_id="svc-tok-001", notify_email=True, notify_sms=False)
    sub = await create_subscription(db_session, user, req)

    token = create_unsubscribe_token(sub.id, user.id, settings)
    await unsubscribe_by_token(db_session, token, settings)

    result = await db_session.execute(select(Subscription).where(Subscription.id == sub.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_service_unsubscribe_by_token_wrong_user(db_session, settings):
    from fastapi import HTTPException
    from app.services.subscription_service import create_subscription, unsubscribe_by_token
    from app.schemas.subscription import CreateSubscriptionRequest

    user = await _make_user(db_session, "svc_wrong@example.com")
    req = CreateSubscriptionRequest(type="launch", ll2_id="svc-tok-002", notify_email=True, notify_sms=False)
    sub = await create_subscription(db_session, user, req)

    token = create_unsubscribe_token(sub.id, 9999, settings)
    with pytest.raises(HTTPException) as exc_info:
        await unsubscribe_by_token(db_session, token, settings)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_service_unsubscribe_malformed_token(db_session, settings):
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    import jwt
    from app.services.subscription_service import unsubscribe_by_token

    payload = {
        "user_id": 1,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.unsubscribe_secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        await unsubscribe_by_token(db_session, token, settings)
    assert exc_info.value.status_code == 400
