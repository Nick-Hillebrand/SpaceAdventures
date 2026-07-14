"""Direct-function coverage tests for router handlers.

pytest-cov doesn't always attribute async lines inside FastAPI route handlers
when called via ASGI transport. Calling the route functions directly forces
proper attribution.
"""
from __future__ import annotations

import unittest.mock as mock
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.n2yo_client import N2YOError


# ---------------------------------------------------------------------------
# Auth router — dependency & route direct-call tests
# ---------------------------------------------------------------------------


async def test_get_current_user_dep_no_auth_header(db_session, settings):
    """No Authorization header → 401."""
    from app.routers.auth import get_current_user_dep

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_dep(
            authorization=None,
            session=db_session,
            settings=settings,
        )
    assert exc_info.value.status_code == 401


async def test_get_current_user_dep_invalid_bearer(db_session, settings):
    """Invalid Bearer token → 401."""
    from app.routers.auth import get_current_user_dep

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_dep(
            authorization="Bearer notavalidtoken",
            session=db_session,
            settings=settings,
        )
    assert exc_info.value.status_code == 401


async def test_get_current_user_dep_valid_token(db_session, settings):
    """Valid token → returns User object (covers `return user`)."""
    from app.routers.auth import get_current_user_dep
    from app.services import auth_service

    user_data = {
        "first_name": "Dep",
        "last_name": "Test",
        "email": "dep_test@example.com",
        "password": "testpassword",
    }
    user = await auth_service.register_user(db_session, user_data, settings)
    token = auth_service.create_access_token(user.id, settings)

    result = await get_current_user_dep(
        authorization=f"Bearer {token}",
        session=db_session,
        settings=settings,
    )
    assert result.id == user.id


async def test_register_route_duplicate_raises_422(db_session, settings):
    """Duplicate registration triggers REGISTRATION_FAILED ValueError → 422."""
    from app.routers.auth import register
    from app.schemas.auth import RegisterRequest

    body = RegisterRequest(
        first_name="Dup",
        last_name="User",
        email="dup_route@example.com",
        password="testpassword",
    )
    request = MagicMock()
    request.app.state.settings = settings

    # Register first time succeeds
    await register(body=body, session=db_session, settings=settings)

    # Second time raises ValueError → JSONResponse 422
    from fastapi.responses import JSONResponse
    response = await register(body=body, session=db_session, settings=settings)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 422


async def test_verify_email_invalid_otp_raises_400(db_session, settings):
    """Wrong OTP in verify_email → HTTPException 400."""
    from app.routers.auth import verify_email
    from app.schemas.auth import VerifyOtpRequest
    from app.services import auth_service

    user = await auth_service.register_user(
        db_session,
        {"first_name": "V", "last_name": "E", "email": "ve@example.com", "password": "testpassword"},
        settings,
    )
    body = VerifyOtpRequest(otp="000000")

    with pytest.raises(HTTPException) as exc_info:
        await verify_email(body=body, current_user=user, session=db_session)
    assert exc_info.value.status_code == 400


async def test_verify_phone_invalid_otp_raises_400(db_session, settings):
    """Wrong OTP in verify_phone → HTTPException 400."""
    from app.routers.auth import verify_phone
    from app.schemas.auth import VerifyOtpRequest
    from app.services import auth_service

    user = await auth_service.register_user(
        db_session,
        {"first_name": "V", "last_name": "P", "phone": "+15550001234", "password": "testpassword"},
        settings,
    )
    body = VerifyOtpRequest(otp="000000")

    with pytest.raises(HTTPException) as exc_info:
        await verify_phone(body=body, current_user=user, session=db_session)
    assert exc_info.value.status_code == 400


async def test_resend_otp_route_rate_limit(db_session, settings):
    """Rate-limited OTP resend → HTTPException 429."""
    from app.routers.auth import resend_otp
    from app.schemas.auth import ResendOtpRequest
    from app.services import auth_service

    user = await auth_service.register_user(
        db_session,
        {"first_name": "R", "last_name": "L", "email": "rl@example.com", "password": "testpassword"},
        settings,
    )
    # registration creates 1 OTP; add 5 more via service = 6 total → 7th will rate limit
    for _ in range(5):
        await auth_service.resend_otp(db_session, user.id, "email", settings)

    body = ResendOtpRequest(channel="email")

    with pytest.raises(HTTPException) as exc_info:
        await resend_otp(body=body, current_user=user, session=db_session, settings=settings)
    assert exc_info.value.status_code == 429


async def test_login_route_wrong_password(db_session, settings):
    """Wrong password → HTTPException 401."""
    from app.routers.auth import login
    from app.schemas.auth import LoginRequest
    from app.services import auth_service

    await auth_service.register_user(
        db_session,
        {"first_name": "L", "last_name": "W", "email": "lw@example.com", "password": "testpassword"},
        settings,
    )
    body = LoginRequest(email_or_phone="lw@example.com", password="wrongpassword")
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    response = Response()

    with pytest.raises(HTTPException) as exc_info:
        await login(body=body, request=request, response=response, session=db_session, settings=settings)
    assert exc_info.value.status_code == 401


async def test_login_route_rate_limited(db_session, settings):
    """Rate-limited login → JSONResponse 429."""
    from app.routers.auth import login
    from app.schemas.auth import LoginRequest
    from app.services import auth_service
    from fastapi.responses import JSONResponse

    await auth_service.register_user(
        db_session,
        {"first_name": "RL", "last_name": "L", "email": "rll@example.com", "password": "testpassword"},
        settings,
    )
    body = LoginRequest(email_or_phone="rll@example.com", password="wrongpassword")
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    response = Response()

    # Exhaust rate limit via service (faster than HTTP)
    for _ in range(5):
        try:
            await auth_service.login(db_session, "rll@example.com", "wrongpassword", "127.0.0.1", settings)
        except ValueError:
            pass

    result = await login(body=body, request=request, response=response, session=db_session, settings=settings)
    assert isinstance(result, JSONResponse)
    assert result.status_code == 429


async def test_refresh_route_invalid_token(db_session, settings):
    """Invalid refresh token → HTTPException 401."""
    from app.routers.auth import refresh
    from app.schemas.auth import RefreshRequest

    body = RefreshRequest(refresh_token="notavalidtoken")
    request = MagicMock()
    request.cookies = {}
    response = Response()
    with pytest.raises(HTTPException) as exc_info:
        await refresh(request=request, response=response, session=db_session, settings=settings, body=body)
    assert exc_info.value.status_code == 401


async def test_logout_route_invalid_token(db_session, settings):
    """Invalid refresh token → HTTPException 401."""
    from app.routers.auth import logout
    from app.schemas.auth import LogoutRequest

    body = LogoutRequest(refresh_token="notavalidtoken")
    request = MagicMock()
    request.cookies = {}
    response = Response()
    with pytest.raises(HTTPException) as exc_info:
        await logout(request=request, response=response, session=db_session, settings=settings, body=body)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# ISS router — direct N2YOError exception path tests
# ---------------------------------------------------------------------------


async def test_iss_positions_n2yo_error_direct(db_session):
    """N2YOError in get_positions raises HTTPException via router."""
    from app.routers.iss import get_positions

    mock_client = AsyncMock()
    with patch("app.services.iss_service.get_positions", side_effect=N2YOError("N2YO_ERROR", "fail", 502)):
        with pytest.raises(HTTPException) as exc_info:
            await get_positions(session=db_session, client=mock_client, cap=900)
    assert exc_info.value.status_code == 502


async def test_iss_tle_n2yo_error_direct(db_session):
    """N2YOError in get_tle raises HTTPException via router."""
    from app.routers.iss import get_tle

    mock_client = AsyncMock()
    with patch("app.services.iss_service.get_tle", side_effect=N2YOError("N2YO_ERROR", "fail", 502)):
        with pytest.raises(HTTPException) as exc_info:
            await get_tle(session=db_session, client=mock_client, cap=900)
    assert exc_info.value.status_code == 502


async def test_iss_visual_passes_n2yo_error_direct(db_session):
    """N2YOError in get_visual_passes raises HTTPException via router."""
    from app.routers.iss import get_visual_passes

    mock_client = AsyncMock()
    with patch("app.services.iss_service.get_passes", side_effect=N2YOError("N2YO_ERROR", "fail", 502)):
        with pytest.raises(HTTPException) as exc_info:
            await get_visual_passes(
                lat=0.0, lng=0.0, alt=0.0,
                session=db_session, client=mock_client, cap=900,
            )
    assert exc_info.value.status_code == 502


async def test_iss_radio_passes_n2yo_error_direct(db_session):
    """N2YOError in get_radio_passes raises HTTPException via router."""
    from app.routers.iss import get_radio_passes

    mock_client = AsyncMock()
    with patch("app.services.iss_service.get_passes", side_effect=N2YOError("N2YO_ERROR", "fail", 502)):
        with pytest.raises(HTTPException) as exc_info:
            await get_radio_passes(
                lat=0.0, lng=0.0, alt=0.0,
                session=db_session, client=mock_client, cap=900,
            )
    assert exc_info.value.status_code == 502


async def test_iss_quota_direct(db_session):
    """Direct call to get_quota returns IssQuotaResponse."""
    from app.routers.iss import get_quota

    result = await get_quota(session=db_session, cap=900)
    assert result.cap == 900
    assert result.used == 0
    assert result.resets_at > result.window_start


# ---------------------------------------------------------------------------
# main.py — lifespan coverage
# ---------------------------------------------------------------------------


async def test_lifespan_scheduler_disabled_by_default(settings):
    """The web tier never schedules jobs unless SCHEDULER_IN_APP is set
    (17-worker-and-scheduling.md P3.1) — all recurring work lives in
    `app/worker.py`."""
    from app.main import lifespan, create_app

    app = create_app(settings=settings)

    with patch("app.main.register_jobs") as mock_register, \
         patch("app.main.AsyncIOScheduler") as mock_scheduler_cls:
        async with lifespan(app):
            pass

    mock_register.assert_not_called()
    mock_scheduler_cls.assert_not_called()


async def test_lifespan_scheduler_in_app_registers_jobs(settings):
    """SCHEDULER_IN_APP=1 (single-container SQLite dev compose) runs the same
    job registry in-process instead of a dedicated worker container."""
    from app.main import lifespan, create_app

    dev_settings = settings.model_copy(update={"scheduler_in_app": True})
    app = create_app(settings=dev_settings)

    mock_scheduler = MagicMock()
    with patch("app.main.register_jobs") as mock_register, \
         patch("app.main.AsyncIOScheduler", return_value=mock_scheduler):
        async with lifespan(app):
            pass

    mock_register.assert_called_once()
    mock_scheduler.start.assert_called_once()
    mock_scheduler.shutdown.assert_called_once_with(wait=False)


def test_default_settings_no_secrets():
    """_default_settings() works without env secrets when require_secrets=False."""
    import os
    from app.main import _default_settings

    with patch.dict(os.environ, {"APP_REQUIRE_SECRETS": "0"}):
        s = _default_settings()
    assert s is not None


# ---------------------------------------------------------------------------
# main.py — health endpoint helpers direct-call coverage
#
# pytest-cov attributes lines inside a route handler poorly when the route is
# only ever exercised over ASGI transport (see module docstring). `health` is
# defined as a closure inside `create_app`, so it isn't importable directly —
# pull it off the built app's routes instead.
# ---------------------------------------------------------------------------


def _get_health_endpoint(app):
    route = next(r for r in app.routes if r.path == "/api/v1/health")
    return route.endpoint


def test_quota_status_unconfigured_without_api_key(settings):
    from app.main import _quota_status

    no_key_settings = settings.model_copy(update={"n2yo_api_key": ""})
    assert _quota_status(no_key_settings, None) == "unconfigured"


def test_quota_status_ok_when_no_row_yet(settings):
    from app.main import _quota_status

    assert _quota_status(settings, None) == "ok"


def test_quota_status_ok_below_warning_threshold(settings):
    from app.main import _quota_status
    from app.models.n2yo_quota import N2yoQuota

    row = N2yoQuota(id=1, used=1)
    assert _quota_status(settings, row) == "ok"


def test_quota_status_warning_above_90_percent(settings):
    from app.main import _quota_status
    from app.models.n2yo_quota import N2yoQuota

    row = N2yoQuota(id=1, used=int(settings.n2yo_hourly_cap * 0.95))
    assert _quota_status(settings, row) == "warning"


def test_quota_status_exhausted_at_cap(settings):
    from app.main import _quota_status
    from app.models.n2yo_quota import N2yoQuota

    row = N2yoQuota(id=1, used=settings.n2yo_hourly_cap)
    assert _quota_status(settings, row) == "exhausted"


async def test_health_snapshot_ok_path(db_session):
    from app.main import _health_snapshot

    status, job_rows, quota_row, dead_letter_count = await _health_snapshot(db_session)
    assert status == "ok"
    assert job_rows == []
    assert quota_row is None
    assert dead_letter_count == 0


async def test_health_snapshot_error_path_never_raises():
    from app.main import _health_snapshot

    broken_session = AsyncMock()
    broken_session.execute.side_effect = RuntimeError("db is down")

    status, job_rows, quota_row, dead_letter_count = await _health_snapshot(broken_session)
    assert status == "error"
    assert job_rows == []
    assert quota_row is None
    assert dead_letter_count == 0


async def test_health_route_direct_public_degraded_no_heartbeat(db_session, settings):
    from app.main import create_app

    app = create_app(settings=settings)
    health = _get_health_endpoint(app)

    request = MagicMock()
    request.app.state.settings = settings

    result = await health(request=request, credentials=None, session=db_session)
    assert result == {"status": "degraded"}


async def test_health_route_direct_admin_full_response(db_session, settings):
    from app.main import create_app
    from app.models.job_status import JobStatus

    admin_settings = settings.model_copy(update={"admin_api_key": "secret"})
    db_session.add(
        JobStatus(job_name="worker_heartbeat", last_success_at=datetime.now(timezone.utc))
    )
    await db_session.commit()

    app = create_app(settings=admin_settings)
    health = _get_health_endpoint(app)

    request = MagicMock()
    request.app.state.settings = admin_settings
    credentials = MagicMock()
    credentials.credentials = "secret"

    result = await health(request=request, credentials=credentials, session=db_session)
    assert result["status"] == "ok"
    assert result["db"] == "ok"
    assert "jobs" in result
    assert result["jobs"]["worker_heartbeat"] == "ok"


async def test_health_route_direct_stale_job_marks_degraded(db_session, settings):
    from app.main import create_app
    from app.models.job_status import JobStatus

    stale = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(JobStatus(job_name="worker_heartbeat", last_success_at=stale))
    await db_session.commit()

    app = create_app(settings=settings)
    health = _get_health_endpoint(app)

    request = MagicMock()
    request.app.state.settings = settings

    result = await health(request=request, credentials=None, session=db_session)
    assert result == {"status": "degraded"}
