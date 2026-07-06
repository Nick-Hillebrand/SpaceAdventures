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
from fastapi import HTTPException
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

    with pytest.raises(HTTPException) as exc_info:
        await login(body=body, request=request, session=db_session, settings=settings)
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

    # Exhaust rate limit via service (faster than HTTP)
    for _ in range(5):
        try:
            await auth_service.login(db_session, "rll@example.com", "wrongpassword", "127.0.0.1", settings)
        except ValueError:
            pass

    response = await login(body=body, request=request, session=db_session, settings=settings)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 429


async def test_refresh_route_invalid_token(db_session, settings):
    """Invalid refresh token → HTTPException 401."""
    from app.routers.auth import refresh
    from app.schemas.auth import RefreshRequest

    body = RefreshRequest(refresh_token="notavalidtoken")
    with pytest.raises(HTTPException) as exc_info:
        await refresh(body=body, session=db_session, settings=settings)
    assert exc_info.value.status_code == 401


async def test_logout_route_invalid_token(db_session, settings):
    """Invalid refresh token → HTTPException 401."""
    from app.routers.auth import logout
    from app.schemas.auth import LogoutRequest

    body = LogoutRequest(refresh_token="notavalidtoken")
    with pytest.raises(HTTPException) as exc_info:
        await logout(body=body, session=db_session)
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


async def test_lifespan_initial_sync_when_empty(settings):
    """Lifespan runs initial sync when table is empty."""
    from app.main import lifespan, create_app

    app = create_app(settings=settings)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.AsyncSessionLocal", return_value=mock_ctx), \
         patch("app.main.launches_service.is_launches_table_empty", return_value=True) as mock_empty, \
         patch("app.main.launches_service.sync_launches") as mock_sync:

        async with lifespan(app):
            pass  # app is "running"

    mock_sync.assert_called()


async def test_lifespan_skips_sync_when_populated(settings):
    """Lifespan skips initial sync when launches table is not empty."""
    from app.main import lifespan, create_app

    app = create_app(settings=settings)

    mock_session = AsyncMock(spec=AsyncSession)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("app.main.AsyncSessionLocal", return_value=mock_ctx), \
         patch("app.main.launches_service.is_launches_table_empty", return_value=False) as mock_empty, \
         patch("app.main.launches_service.sync_launches") as mock_sync:

        async with lifespan(app):
            pass

    mock_sync.assert_not_called()


def test_default_settings_no_secrets():
    """_default_settings() works without env secrets when require_secrets=False."""
    import os
    from app.main import _default_settings

    with patch.dict(os.environ, {"APP_REQUIRE_SECRETS": "0"}):
        s = _default_settings()
    assert s is not None
