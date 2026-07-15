"""Tests for the ISS_PASS notification content/delivery path
(20-location-and-sky-alerts.md L1) — push-preferred, email-fallback, distinct
from the launch path's independent-per-channel firing in test_notifications.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from passlib.context import CryptContext
from pywebpush import WebPushException
from sqlalchemy import select

from app.models.iss_pass_alert import IssPassAlert
from app.models.notification_log import NotificationLog, PendingNotification
from app.models.push_subscription import PushSubscription
from app.models.subscription import Subscription
from app.models.user import User
from app.services import notification_service
from app.services.notification_service import (
    _build_iss_pass_content,
    _compass_direction,
    _resolve_location_tz,
)

_PWD = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_user(session, email="alice@example.com", location_tz="Europe/Paris") -> User:
    user = User(
        first_name="Alice",
        last_name="Test",
        email=email,
        password_hash=_PWD.hash("pw"),
        email_verified=True,
        is_pro=True,
        location_lat=48.86,
        location_lng=2.35,
        location_tz=location_tz,
    )
    session.add(user)
    return user


async def _make_iss_pass_subscription(
    session, user_id: int, notify_push: bool = True, notify_email: bool = False
) -> Subscription:
    sub = Subscription(
        user_id=user_id, type="iss_pass", notify_push=notify_push, notify_email=notify_email
    )
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


async def _make_alert(session, user_id: int, max_el: float = 45.0) -> IssPassAlert:
    start = datetime.now(timezone.utc) + timedelta(minutes=30)
    alert = IssPassAlert(
        user_id=user_id,
        start_utc=start,
        end_utc=start + timedelta(minutes=4, seconds=20),
        max_el=max_el,
        start_az=270.0,
        end_az=90.0,
        mag=-2.5,
        notified=True,
    )
    session.add(alert)
    await session.flush()
    return alert


async def _make_pending(session, subscription_id: str, iss_pass_alert_id: int) -> PendingNotification:
    pending = PendingNotification(
        subscription_id=subscription_id,
        iss_pass_alert_id=iss_pass_alert_id,
        change_type="ISS_PASS",
        attempt_count=0,
    )
    session.add(pending)
    await session.flush()
    return pending


# ---------------------------------------------------------------------------
# Pure content-building helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "azimuth,expected",
    [(0, "N"), (20, "N"), (46, "NE"), (90, "E"), (180, "S"), (270, "W"), (359, "N"), (315, "NW")],
)
def test_compass_direction(azimuth, expected):
    assert _compass_direction(azimuth) == expected


def test_resolve_location_tz_valid():
    tz = _resolve_location_tz("Europe/Paris")
    assert str(tz) == "Europe/Paris"


def test_resolve_location_tz_none_defaults_utc():
    assert _resolve_location_tz(None) is timezone.utc


def test_resolve_location_tz_invalid_defaults_utc():
    assert _resolve_location_tz("Not/AZone") is timezone.utc


def test_build_iss_pass_content_formats_local_time_and_direction():
    user = User(location_tz="UTC")
    start = datetime(2026, 7, 15, 20, 30, tzinfo=timezone.utc)
    alert = IssPassAlert(
        start_utc=start,
        end_utc=start + timedelta(minutes=4, seconds=20),
        max_el=52.0,
        start_az=270.0,
        end_az=90.0,
    )
    title, body = _build_iss_pass_content(alert, user)
    assert title == "ISS pass visible tonight"
    assert "20:30" in body
    assert "from the W" in body
    assert "52°" in body
    assert "4m 20s" in body


def test_build_iss_pass_content_sub_minute_duration():
    user = User(location_tz="UTC")
    start = datetime(2026, 7, 15, 20, 30, tzinfo=timezone.utc)
    alert = IssPassAlert(
        start_utc=start, end_utc=start + timedelta(seconds=45), max_el=30.0, start_az=0.0, end_az=10.0,
    )
    _, body = _build_iss_pass_content(alert, user)
    assert "45s" in body
    assert "0m" not in body


# ---------------------------------------------------------------------------
# _process_iss_pass_pending via drain_queue — channel policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.notification_service._send_push", new_callable=AsyncMock)
async def test_push_success_deletes_pending_and_logs(mock_send_push, db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    db_session.add(
        PushSubscription(user_id=user.id, endpoint="https://push.example/1", p256dh="k", auth="a")
    )
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=False)
    alert = await _make_alert(db_session, user.id)
    pending = await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    mock_send_push.assert_awaited_once()
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []

    log_result = await db_session.execute(select(NotificationLog))
    logs = list(log_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].channel == "push"
    assert logs[0].iss_pass_alert_id == alert.id
    assert logs[0].change_type == "ISS_PASS"


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_push_failure_falls_back_to_email(mock_send_email, db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    db_session.add(
        PushSubscription(user_id=user.id, endpoint="https://push.example/1", p256dh="k", auth="a")
    )
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=True)
    alert = await _make_alert(db_session, user.id)
    pending = await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()

    with patch("app.services.notification_service.webpush", side_effect=RuntimeError("push down")):
        await notification_service.drain_queue(db_session, settings)

    mock_send_email.assert_awaited_once()
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []

    log_result = await db_session.execute(select(NotificationLog))
    logs = list(log_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].channel == "email"


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_push_gone_devices_pruned_and_falls_back_to_email(mock_send_email, db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    device = PushSubscription(
        user_id=user.id, endpoint="https://push.example/gone", p256dh="k", auth="a"
    )
    db_session.add(device)
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=True)
    alert = await _make_alert(db_session, user.id)
    await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()
    device_id = device.id

    fake_response = MagicMock()
    fake_response.status_code = 410
    gone_exc = WebPushException("gone", response=fake_response)

    with patch("app.services.notification_service.webpush", side_effect=gone_exc):
        await notification_service.drain_queue(db_session, settings)

    mock_send_email.assert_awaited_once()
    db_session.expire_all()
    result = await db_session.execute(
        select(PushSubscription).where(PushSubscription.id == device_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_email_only_when_push_not_enabled(mock_send_email, db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=False, notify_email=True)
    alert = await _make_alert(db_session, user.id)
    await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    mock_send_email.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.services.notification_service._send_push", new_callable=AsyncMock)
@patch("aiosmtplib.send", new_callable=AsyncMock)
async def test_no_channels_requested_drops_pending_silently(mock_send_email, mock_send_push, db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=False, notify_email=False)
    alert = await _make_alert(db_session, user.id)
    await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()

    await notification_service.drain_queue(db_session, settings)

    mock_send_email.assert_not_awaited()
    mock_send_push.assert_not_awaited()
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_alert_missing_drops_pending_without_sending(db_session, settings):
    """`iss_pass_alerts.id` is a CASCADE FK on `pending_notifications`, so a
    real orphan can't be constructed via the ORM (deleting the alert deletes
    the pending row too) — this defensive branch is exercised directly with
    a mocked session instead."""
    user = _make_user(db_session)
    await db_session.flush()
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=True)
    pending = MagicMock(iss_pass_alert_id=999999)
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    await notification_service._process_iss_pass_pending(session, settings, pending, sub, user)

    session.get.assert_awaited_once()
    session.delete.assert_awaited_once_with(pending)


@pytest.mark.asyncio
async def test_both_channels_fail_reschedules_with_backoff(db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    db_session.add(
        PushSubscription(user_id=user.id, endpoint="https://push.example/1", p256dh="k", auth="a")
    )
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=True)
    alert = await _make_alert(db_session, user.id)
    pending = await _make_pending(db_session, sub.id, alert.id)
    await db_session.commit()
    pending_id = pending.id

    with patch(
        "app.services.notification_service.webpush", side_effect=RuntimeError("push down")
    ), patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=RuntimeError("smtp down")):
        await notification_service.drain_queue(db_session, settings)

    db_session.expire_all()
    row = await db_session.get(PendingNotification, pending_id)
    assert row is not None
    assert row.attempt_count == 1
    assert row.dead is False
    assert row.next_attempt_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_both_channels_fail_dead_letters_after_max_attempts(db_session, settings):
    user = _make_user(db_session)
    await db_session.flush()
    db_session.add(
        PushSubscription(user_id=user.id, endpoint="https://push.example/1", p256dh="k", auth="a")
    )
    sub = await _make_iss_pass_subscription(db_session, user.id, notify_push=True, notify_email=True)
    alert = await _make_alert(db_session, user.id)
    pending = await _make_pending(db_session, sub.id, alert.id)
    pending.attempt_count = notification_service._MAX_ATTEMPTS - 1
    await db_session.commit()
    pending_id = pending.id
    alert_id = alert.id

    with patch(
        "app.services.notification_service.webpush", side_effect=RuntimeError("push down")
    ), patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=RuntimeError("smtp down")):
        await notification_service.drain_queue(db_session, settings)

    db_session.expire_all()
    row = await db_session.get(PendingNotification, pending_id)
    assert row.dead is True

    log_result = await db_session.execute(select(NotificationLog))
    logs = list(log_result.scalars().all())
    assert len(logs) == 1
    assert logs[0].delivery_status == "failed"
    assert logs[0].iss_pass_alert_id == alert_id
