"""Branch-coverage tests for error paths not exercised elsewhere.

Covers the client-missing 503 dependencies (mars/neo/space_weather), the
APOD translator paths, N2YO client error branches, and notification
delivery edge branches.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.config import Settings
from app.models import Apod
from app.models.launches import Launch
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.models.user import User
from app.services import apod_service, notification_service
from app.services.n2yo_client import N2YOClient, N2YOError
from app.services.notification_service import _change_label, _send_email, _send_sms


def _bare_request() -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


# ---------------------------------------------------------------------------
# Client-missing dependencies → 503
# ---------------------------------------------------------------------------


def test_mars_client_dep_missing_returns_503():
    from app.routers.mars import _get_mars_client

    with pytest.raises(HTTPException) as exc_info:
        _get_mars_client(_bare_request())
    assert exc_info.value.status_code == 503


def test_neo_client_dep_missing_returns_503():
    from app.routers.neo import _get_nasa_client

    with pytest.raises(HTTPException) as exc_info:
        _get_nasa_client(_bare_request())
    assert exc_info.value.status_code == 503


def test_space_weather_client_dep_missing_returns_503():
    from app.routers.space_weather import _get_nasa_client

    with pytest.raises(HTTPException) as exc_info:
        _get_nasa_client(_bare_request())
    assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# APOD translator paths
# ---------------------------------------------------------------------------


_APOD_PAYLOAD = {
    "date": "2020-01-01",
    "title": "Sun",
    "explanation": "A star.",
    "url": "https://apod.nasa.gov/x.jpg",
    "media_type": "image",
}


async def _ok_translator(fields):
    return {"de": {k: f"DE:{v}" for k, v in fields.items()}}


async def _failing_translator(fields):
    raise RuntimeError("translator down")


async def test_fetch_apod_fresh_fetch_translates(db_session):
    client = MagicMock()
    client.get = AsyncMock(return_value=_APOD_PAYLOAD)

    result = await apod_service.fetch_apod(
        db_session, client, "2020-01-01", translator=_ok_translator
    )
    assert result.row.translations_json is not None
    assert result.row.translations_json["de"]["title"] == "DE:Sun"


async def test_fetch_apod_cached_row_fills_missing_translations(db_session):
    db_session.add(
        Apod(
            date="2020-01-02",
            title="Moon",
            explanation="A moon.",
            url="https://apod.nasa.gov/m.jpg",
            media_type="image",
            fetched_at=datetime(2020, 1, 2),
            translations_json=None,
        )
    )
    await db_session.commit()

    client = MagicMock()
    client.get = AsyncMock(side_effect=AssertionError("should not hit upstream"))
    result = await apod_service.fetch_apod(
        db_session, client, "2020-01-02", translator=_ok_translator
    )
    assert result.cached is True
    assert result.row.translations_json["de"]["title"] == "DE:Moon"


async def test_fetch_apod_translator_failure_is_swallowed(db_session):
    client = MagicMock()
    client.get = AsyncMock(return_value=_APOD_PAYLOAD)

    result = await apod_service.fetch_apod(
        db_session, client, "2020-01-01", translator=_failing_translator
    )
    assert result.row.translations_json is None


# ---------------------------------------------------------------------------
# N2YO client error branches
# ---------------------------------------------------------------------------


def _n2yo(mock_client: MagicMock) -> N2YOClient:
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        n2yo_api_key="k",
        n2yo_base_url="https://n2yo.example",
    )
    return N2YOClient(settings, client=mock_client)


async def test_n2yo_connect_error():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(N2YOError) as exc_info:
        await _n2yo(mock_client).get_tle()
    assert exc_info.value.code == "N2YO_UNAVAILABLE"


async def test_n2yo_timeout_error():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(N2YOError) as exc_info:
        await _n2yo(mock_client).get_tle()
    assert exc_info.value.code == "N2YO_UNAVAILABLE"


async def test_n2yo_http_status_error():
    response = MagicMock(status_code=500)
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)
    with pytest.raises(N2YOError) as exc_info:
        await _n2yo(mock_client).get_tle()
    assert exc_info.value.code == "N2YO_UNAVAILABLE"


async def test_n2yo_invalid_json():
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("not json")
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=response)
    with pytest.raises(N2YOError) as exc_info:
        await _n2yo(mock_client).get_tle()
    assert exc_info.value.code == "N2YO_ERROR"


def test_n2yo_client_property():
    mock_client = MagicMock()
    assert _n2yo(mock_client).client is mock_client


# ---------------------------------------------------------------------------
# Notification delivery edge branches
# ---------------------------------------------------------------------------


def test_change_label_unknown_type_passthrough():
    assert _change_label("SOMETHING_ELSE", None, None) == "SOMETHING_ELSE"


def _smtp_settings(port: int) -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        smtp_host="smtp.example",
        smtp_port=port,
        smtp_user="u",
        smtp_password="p",
        smtp_from="noreply@example.com",
    )


async def test_send_email_uses_implicit_tls_on_465():
    send = AsyncMock()
    with patch("aiosmtplib.send", send):
        await _send_email(
            _smtp_settings(465), "to@example.com", "S", "T", "<p>H</p>", "https://u.example"
        )
    assert send.await_args.kwargs["use_tls"] is True
    assert "start_tls" not in send.await_args.kwargs


async def test_send_email_uses_starttls_on_587():
    send = AsyncMock()
    with patch("aiosmtplib.send", send):
        await _send_email(
            _smtp_settings(587), "to@example.com", "S", "T", "<p>H</p>", "https://u.example"
        )
    assert send.await_args.kwargs["start_tls"] is True


async def test_send_sms_calls_twilio():
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        twilio_account_sid="sid",
        twilio_auth_token="tok",
        twilio_from_number="+15550000000",
    )
    with patch("twilio.rest.Client") as MockClient:
        await _send_sms(settings, "+15551112222", "hello")
    MockClient.assert_called_once_with("sid", "tok")
    MockClient.return_value.messages.create.assert_called_once_with(
        to="+15551112222", from_="+15550000000", body="hello"
    )


def _user(session, phone: str | None = None) -> User:
    user = User(
        first_name="Alice",
        last_name="Test",
        email="alice@example.com",
        phone=phone,
        password_hash="x",
        email_verified=True,
        phone_verified=phone is not None,
    )
    session.add(user)
    return user


async def _subscription(session, user_id: int, **kwargs) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        type="launch",
        ll2_id="launch-001",
        notify_email=kwargs.get("notify_email", True),
        notify_sms=kwargs.get("notify_sms", False),
    )
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


def _pending(session, subscription_id: str, ll2_id: str = "launch-001") -> PendingNotification:
    pending = PendingNotification(
        subscription_id=subscription_id,
        ll2_id=ll2_id,
        change_type="NET_SLIP",
        old_value="a",
        new_value="b",
        attempt_count=0,
    )
    session.add(pending)
    return pending


async def test_drain_drops_pending_when_launch_deleted(db_session, settings):
    user = _user(db_session)
    await db_session.flush()
    sub = await _subscription(db_session, user.id)
    _pending(db_session, sub.id, ll2_id="no-such-launch")
    await db_session.commit()

    with patch("aiosmtplib.send", AsyncMock()) as send:
        await notification_service.drain_queue(db_session, settings)

    send.assert_not_awaited()
    from sqlalchemy import select

    remaining = (await db_session.execute(select(PendingNotification))).scalars().all()
    assert remaining == []


async def test_drain_concatenates_email_and_sms_errors(db_session, settings):
    user = _user(db_session, phone="+15551112222")
    await db_session.flush()
    sub = await _subscription(db_session, user.id, notify_email=True, notify_sms=True)
    launch = Launch(
        ll2_id="launch-001",
        name="Falcon 9",
        net=datetime(2026, 8, 1, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX",
        rocket_name="Falcon 9",
        pad_name="LC-39A",
        pad_location="Florida",
        livestream_urls=[],
        fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db_session.add(launch)
    _pending(db_session, sub.id)
    await db_session.commit()

    with (
        patch("aiosmtplib.send", AsyncMock(side_effect=RuntimeError("smtp down"))),
        patch(
            "app.services.notification_service._send_sms",
            AsyncMock(side_effect=RuntimeError("twilio down")),
        ),
    ):
        await notification_service.drain_queue(db_session, settings)

    from sqlalchemy import select

    pending = (await db_session.execute(select(PendingNotification))).scalars().one()
    assert pending.attempt_count == 1
