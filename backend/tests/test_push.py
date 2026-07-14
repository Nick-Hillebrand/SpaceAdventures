"""Tests for Web Push subscribe/unsubscribe endpoints (19-notification-channels-v2.md B1.2)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.push_subscription import PushSubscription
from app.services import auth_service, push_service
from app.schemas.push import PushSubscribeRequest, PushSubscriptionKeys

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


SUBSCRIBE_BODY = {
    "endpoint": "https://push.example/endpoint-1",
    "keys": {"p256dh": "test-p256dh-key", "auth": "test-auth-secret"},
}


# ---------------------------------------------------------------------------
# vapid-public-key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vapid_public_key_is_public(client, settings):
    r = await client.get("/api/v1/push/vapid-public-key")
    assert r.status_code == 200
    assert r.json() == {"public_key": settings.vapid_public_key}


# ---------------------------------------------------------------------------
# subscribe (HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_creates_row(client, db_session):
    _, headers = await _register_and_login(client)
    r = await client.post("/api/v1/push/subscribe", json=SUBSCRIBE_BODY, headers=headers)
    assert r.status_code == 204

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == SUBSCRIBE_BODY["endpoint"])
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.p256dh == "test-p256dh-key"


@pytest.mark.asyncio
async def test_subscribe_unauthenticated(client):
    r = await client.post("/api/v1/push/subscribe", json=SUBSCRIBE_BODY)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_subscribe_upserts_on_endpoint(client, db_session):
    """Re-subscribing the same browser (e.g. after a key rotation) must
    update the existing row, not create a duplicate."""
    _, headers = await _register_and_login(client)
    r1 = await client.post("/api/v1/push/subscribe", json=SUBSCRIBE_BODY, headers=headers)
    assert r1.status_code == 204

    updated_body = {
        "endpoint": SUBSCRIBE_BODY["endpoint"],
        "keys": {"p256dh": "rotated-key", "auth": "rotated-auth"},
    }
    r2 = await client.post("/api/v1/push/subscribe", json=updated_body, headers=headers)
    assert r2.status_code == 204

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == SUBSCRIBE_BODY["endpoint"])
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].p256dh == "rotated-key"


# ---------------------------------------------------------------------------
# subscribe — SSRF guard on endpoint (25-security-testing.md §2.5 threat
# model: "a malicious registered user" can hand the API any endpoint URL
# directly, bypassing the browser's PushManager entirely; the worker later
# POSTs to it via pywebpush)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_endpoint",
    [
        "http://push.example/endpoint-1",  # non-https
        "https://127.0.0.1/x",  # loopback
        "https://169.254.169.254/latest/meta-data/",  # cloud metadata
        "https://10.0.0.5/x",  # RFC1918 private
        "https://192.168.1.1/x",  # RFC1918 private
        "https://[::1]/x",  # IPv6 loopback
        "ftp://push.example/x",  # non-https scheme entirely
        "not-a-url",
    ],
)
@pytest.mark.asyncio
async def test_subscribe_rejects_unsafe_endpoint(client, bad_endpoint):
    _, headers = await _register_and_login(client)
    body = {"endpoint": bad_endpoint, "keys": SUBSCRIBE_BODY["keys"]}
    r = await client.post("/api/v1/push/subscribe", json=body, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_accepts_realistic_push_service_endpoints(client):
    """Real push services (FCM, Mozilla autopush) use https + hostnames, not
    IP literals — confirm the SSRF guard doesn't false-positive on these."""
    _, headers = await _register_and_login(client)
    for endpoint in [
        "https://fcm.googleapis.com/fcm/send/abc123",
        "https://updates.push.services.mozilla.com/wpush/v2/xyz",
        "https://8.8.8.8/x",  # public IP literal — allowed (only private/reserved are blocked)
    ]:
        r = await client.post(
            "/api/v1/push/subscribe",
            json={"endpoint": endpoint, "keys": SUBSCRIBE_BODY["keys"]},
            headers=headers,
        )
        assert r.status_code == 204, r.text


# ---------------------------------------------------------------------------
# unsubscribe (HTTP) — IDOR prevention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unsubscribe_deletes_own_row(client, db_session):
    _, headers = await _register_and_login(client)
    await client.post("/api/v1/push/subscribe", json=SUBSCRIBE_BODY, headers=headers)

    r = await client.request(
        "DELETE",
        "/api/v1/push/subscribe",
        json={"endpoint": SUBSCRIBE_BODY["endpoint"]},
        headers=headers,
    )
    assert r.status_code == 204

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == SUBSCRIBE_BODY["endpoint"])
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unsubscribe_unauthenticated(client):
    r = await client.request(
        "DELETE", "/api/v1/push/subscribe", json={"endpoint": "https://push.example/x"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unsubscribe_wrong_user_is_404(client):
    """Bob must not be able to delete Alice's push subscription (IDOR)."""
    _, alice_headers = await _register_and_login(client, REGISTER_PAYLOAD)
    await client.post("/api/v1/push/subscribe", json=SUBSCRIBE_BODY, headers=alice_headers)

    _, bob_headers = await _register_and_login(client, REGISTER_PAYLOAD_BOB)
    r = await client.request(
        "DELETE",
        "/api/v1/push/subscribe",
        json={"endpoint": SUBSCRIBE_BODY["endpoint"]},
        headers=bob_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unsubscribe_not_found_is_404(client):
    _, headers = await _register_and_login(client)
    r = await client.request(
        "DELETE",
        "/api/v1/push/subscribe",
        json={"endpoint": "https://push.example/does-not-exist"},
        headers=headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Service-level unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_subscribe_creates_then_upserts(db_session):
    from app.models.user import User

    user = User(
        first_name="Svc",
        last_name="Push",
        email="svc_push_unit@example.com",
        password_hash=auth_service.hash_password("pw"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    req = PushSubscribeRequest(
        endpoint="https://push.example/svc-1",
        keys=PushSubscriptionKeys(p256dh="k1", auth="a1"),
    )
    sub = await push_service.subscribe(db_session, user.id, req)
    assert sub.p256dh == "k1"

    req2 = PushSubscribeRequest(
        endpoint="https://push.example/svc-1",
        keys=PushSubscriptionKeys(p256dh="k2", auth="a2"),
    )
    sub2 = await push_service.subscribe(db_session, user.id, req2)
    assert sub2.id == sub.id
    assert sub2.p256dh == "k2"


@pytest.mark.asyncio
async def test_service_unsubscribe_deletes_own_row(db_session):
    from app.models.user import User

    user = User(
        first_name="Svc",
        last_name="Push",
        email="svc_push_unsub@example.com",
        password_hash=auth_service.hash_password("pw"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    req = PushSubscribeRequest(
        endpoint="https://push.example/svc-unsub-1",
        keys=PushSubscriptionKeys(p256dh="k1", auth="a1"),
    )
    await push_service.subscribe(db_session, user.id, req)

    await push_service.unsubscribe(db_session, user.id, req.endpoint)

    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == req.endpoint)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_service_unsubscribe_not_found_raises_404(db_session):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await push_service.unsubscribe(db_session, 999, "https://push.example/none")
    assert exc_info.value.status_code == 404
