"""Tests for notification_service.drain_queue."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.launches import Launch
from app.models.notification_log import NotificationLog, PendingNotification
from app.models.subscription import Subscription
from app.models.user import User
from app.services import notification_service
from app.services.notification_service import (
    create_unsubscribe_token,
    sanitise,
    scrub_error,
    _build_sms_body,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_user(
    session,
    email: str = "alice@example.com",
    email_verified: bool = True,
    phone: str | None = None,
    phone_verified: bool = False,
) -> User:
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        first_name="Alice",
        last_name="Test",
        email=email,
        phone=phone,
        password_hash=pwd_ctx.hash("pw"),
        email_verified=email_verified,
        phone_verified=phone_verified,
    )
    session.add(user)
    return user


def _make_launch(session, ll2_id: str = "launch-001", name: str = "Falcon 9 Mission") -> Launch:
    launch = Launch(
        ll2_id=ll2_id,
        name=name,
        net=datetime(2026, 8, 1, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX",
        agency_type="Commercial",
        rocket_name="Falcon 9",
        rocket_family="Falcon",
        pad_name="LC-39A",
        pad_location="Florida, USA",
        livestream_urls="[]",
        fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(launch)
    return launch


async def _make_subscription(
    session,
    user_id: int,
    ll2_id: str = "launch-001",
    sub_type: str = "launch",
    notify_email: bool = True,
    notify_sms: bool = False,
) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        type=sub_type,
        ll2_id=ll2_id if sub_type == "launch" else None,
        agency_name="SpaceX" if sub_type == "agency" else None,
        notify_email=notify_email,
        notify_sms=notify_sms,
    )
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


async def _make_pending(session, subscription_id: str, ll2_id: str = "launch-001") -> PendingNotification:
    pending = PendingNotification(
        subscription_id=subscription_id,
        ll2_id=ll2_id,
        change_type="NET_SLIP",
        old_value="2026-08-01T10:00:00",
        new_value="2026-08-01T14:00:00",
        attempt_count=0,
    )
    session.add(pending)
    await session.flush()
    return pending


# ---------------------------------------------------------------------------
# Email notification tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_email_sent_on_net_slip(mock_send, db_session, settings):
    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True, notify_sms=False)
    await _make_pending(db_session, sub.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    assert mock_send.called
    call_kwargs = mock_send.call_args
    msg = call_kwargs.args[0]
    assert "alice@example.com" in msg["To"]


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_email_includes_list_unsubscribe_headers(mock_send, db_session, settings):
    """P1.8: every notification email carries a valid one-click unsubscribe header pair."""
    import jwt as _jwt

    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True, notify_sms=False)
    await _make_pending(db_session, sub.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    msg = mock_send.call_args.args[0]
    list_unsubscribe = msg["List-Unsubscribe"]
    assert list_unsubscribe.startswith("<") and list_unsubscribe.endswith(">")
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    token = list_unsubscribe.strip("<>").split("token=", 1)[1]
    payload = _jwt.decode(token, settings.unsubscribe_secret_key, algorithms=["HS256"])
    assert payload["subscription_id"] == sub.id
    assert payload["user_id"] == user.id


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_email_not_sent_when_unverified(mock_send, db_session, settings):
    user = _make_user(db_session, email_verified=False)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True, notify_sms=False)
    await _make_pending(db_session, sub.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    assert not mock_send.called


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_email_not_sent_when_notify_false(mock_send, db_session, settings):
    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=False, notify_sms=False)
    await _make_pending(db_session, sub.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    assert not mock_send.called


# ---------------------------------------------------------------------------
# SMS notification tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.notification_service._send_sms", new_callable=AsyncMock)
async def test_sms_sent_on_status_change(mock_send_sms, db_session, settings):
    user = _make_user(
        db_session,
        email_verified=False,
        phone="+15551234567",
        phone_verified=True,
    )
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=False, notify_sms=True)
    pending = PendingNotification(
        subscription_id=sub.id,
        ll2_id="launch-001",
        change_type="STATUS_CHANGE",
        old_value="TBD",
        new_value="Go",
        attempt_count=0,
    )
    db_session.add(pending)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    assert mock_send_sms.called
    # Check via call_args_list — drain_queue calls _send_sms(settings, to=user.phone, body=...)
    all_calls = mock_send_sms.call_args_list
    assert len(all_calls) == 1
    ca = all_calls[0]
    # Phone number may be positional or keyword depending on how drain_queue calls it
    phone_found = (
        (len(ca.args) > 1 and ca.args[1] == "+15551234567")
        or ca.kwargs.get("to") == "+15551234567"
    )
    assert phone_found, f"Expected +15551234567 in call: {ca}"


@pytest.mark.asyncio
@patch("app.services.notification_service._send_sms", new_callable=AsyncMock)
async def test_sms_not_sent_when_unverified(mock_send_sms, db_session, settings):
    user = _make_user(
        db_session,
        email_verified=False,
        phone="+15551234567",
        phone_verified=False,
    )
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=False, notify_sms=True)
    await _make_pending(db_session, sub.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    assert not mock_send_sms.called


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_notification_deleted_on_success(mock_send, db_session, settings):
    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True)
    pending = await _make_pending(db_session, sub.id)
    pending_id = pending.id
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    # PendingNotification should be deleted
    result = await db_session.execute(
        select(PendingNotification).where(PendingNotification.id == pending_id)
    )
    assert result.scalar_one_or_none() is None

    # NotificationLog should have a 'sent' record
    log_result = await db_session.execute(
        select(NotificationLog).where(NotificationLog.delivery_status == "sent")
    )
    logs = list(log_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].channel == "email"


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_notification_retry_on_failure(mock_send, db_session, settings):
    mock_send.side_effect = Exception("SMTP connection error")

    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True)
    pending = await _make_pending(db_session, sub.id)
    pending_id = pending.id
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    # Should increment attempt_count, not delete
    db_session.expire_all()
    result = await db_session.execute(
        select(PendingNotification).where(PendingNotification.id == pending_id)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.attempt_count == 1


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_notification_deleted_after_3_failures(mock_send, db_session, settings):
    mock_send.side_effect = Exception("SMTP permanent error")

    user = _make_user(db_session, email_verified=True)
    launch = _make_launch(db_session)
    await db_session.flush()
    await db_session.refresh(user)

    sub = await _make_subscription(db_session, user.id, notify_email=True)
    pending = PendingNotification(
        subscription_id=sub.id,
        ll2_id="launch-001",
        change_type="NET_SLIP",
        old_value="2026-08-01T10:00:00",
        new_value="2026-08-01T14:00:00",
        attempt_count=2,  # Already at 2 — next failure should purge
    )
    db_session.add(pending)
    await db_session.flush()
    pending_id = pending.id
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    # Row should be deleted
    db_session.expire_all()
    result = await db_session.execute(
        select(PendingNotification).where(PendingNotification.id == pending_id)
    )
    assert result.scalar_one_or_none() is None

    # A 'failed' log should exist
    log_result = await db_session.execute(
        select(NotificationLog).where(NotificationLog.delivery_status == "failed")
    )
    logs = list(log_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].error_detail is not None


# ---------------------------------------------------------------------------
# Content / sanitisation tests
# ---------------------------------------------------------------------------


def test_email_subject_sanitised():
    """Control characters in launch name must be stripped."""
    name_with_ctrl = "Falcon 9\r\nInjection Attack"
    sanitised = sanitise(name_with_ctrl)
    assert "\r" not in sanitised
    assert "\n" not in sanitised
    assert "Injection Attack" in sanitised


def test_sms_truncated_to_160_chars():
    """SMS body must not exceed 160 characters even with a long launch name."""

    class _FakeLaunch:
        name = "A" * 200
        net = datetime(2026, 8, 1, 12, 0, 0)
        agency_name = "SpaceX"
        rocket_name = "Falcon 9"

    body = _build_sms_body(_FakeLaunch(), "NET_SLIP", "2026-08-01T10:00:00", "2026-08-01T14:00:00")  # type: ignore[arg-type]
    assert len(body) <= 160


def test_unsubscribe_token_uses_correct_key(settings):
    """Unsubscribe token should be signed with UNSUBSCRIBE_SECRET_KEY, not JWT_SECRET_KEY."""
    import jwt

    settings2 = settings.model_copy(
        update={
            "unsubscribe_secret_key": "unsubscribe-test-key",
            "jwt_secret_key": "jwt-test-key",
        }
    )
    token = create_unsubscribe_token("sub-abc", 1, settings2)

    # Should decode with unsubscribe key
    payload = jwt.decode(token, "unsubscribe-test-key", algorithms=["HS256"])
    assert payload["subscription_id"] == "sub-abc"

    # Should NOT decode with JWT key
    import pytest as _pytest
    with _pytest.raises(jwt.PyJWTError):
        jwt.decode(token, "jwt-test-key", algorithms=["HS256"])


def test_scrub_error_removes_credentials():
    """scrub_error must redact sensitive words from exception details."""

    class FakeErr(Exception):
        pass

    exc = FakeErr("Connection with password=mysecret failed")
    scrubbed = scrub_error(exc)
    assert "mysecret" not in scrubbed
    assert "[REDACTED]" in scrubbed
    assert len(scrubbed) <= 500
