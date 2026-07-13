"""Tests for the security hardening pass.

Covers:
- HTML escaping of untrusted LL2 fields in notification emails
- constant-time admin key check on POST /launches/sync
- LL2 pagination 'next' URL validation (no off-host requests)
- upstream URL sanitisation before storage (APOD / launches / Mars / NEO)
- registration input limits
- OTP codes kept out of production logs
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings
from app.models.launches import Launch
from app.routers.launches import _require_admin
from app.schemas.auth import RegisterRequest
from app.services import auth_service, notification_service
from app.services.apod_service import _apod_from_payload
from app.services.launches_service import _parse_raw
from app.services.ll2_client import LL2Client, LL2ClientError
from app.services.mars_service import _row_from_photo
from app.services.neo_service import _neo_from_object


# ---------------------------------------------------------------------------
# Notification email escaping
# ---------------------------------------------------------------------------


def _make_launch(name: str = "Falcon 9 | Starlink") -> Launch:
    return Launch(
        ll2_id="launch-001",
        name=name,
        net=datetime(2026, 7, 10, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX <b>Corp</b>",
        rocket_name='Falcon "9"',
        pad_name="SLC-40",
        pad_location="Cape Canaveral",
        livestream_urls=[],
    )


def test_email_html_escapes_untrusted_launch_fields():
    launch = _make_launch(name='<script>alert("xss")</script>')
    subject, body_text, body_html = notification_service._build_email_content(
        launch, "NEW_LAUNCH", None, None, "https://spaceadventures.app/u?token=abc"
    )
    assert "<script>" not in body_html
    assert "&lt;script&gt;" in body_html
    assert "<b>Corp</b>" not in body_html
    assert "&lt;b&gt;Corp&lt;/b&gt;" in body_html
    # Plaintext part is not HTML-escaped (different output context)
    assert 'alert("xss")' in body_text


def test_email_html_escapes_change_detail_and_url():
    launch = _make_launch()
    _, _, body_html = notification_service._build_email_content(
        launch,
        "STATUS_CHANGE",
        '<img src=x onerror=alert(1)>',
        "Go",
        'https://spaceadventures.app/u?token=a"><script>x</script>',
    )
    assert "onerror" not in body_html or "&lt;img" in body_html
    assert "<img src=x" not in body_html
    assert '"><script>' not in body_html


# ---------------------------------------------------------------------------
# Admin key check (constant-time, still enforces auth)
# ---------------------------------------------------------------------------


def _mock_request(settings: Settings, auth_header: str | None) -> MagicMock:
    request = MagicMock()
    request.app.state.settings = settings
    request.headers = {"Authorization": auth_header} if auth_header else {}
    return request


def _admin_settings(key: str) -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        admin_api_key=key,
    )


def test_require_admin_no_key_configured_returns_503():
    request = _mock_request(_admin_settings(""), "Bearer whatever")
    with pytest.raises(HTTPException) as exc_info:
        _require_admin(request, None)
    assert exc_info.value.status_code == 503


def test_require_admin_wrong_key_returns_401():
    request = _mock_request(_admin_settings("real-admin-key"), "Bearer wrong-key")
    with pytest.raises(HTTPException) as exc_info:
        _require_admin(request, None)
    assert exc_info.value.status_code == 401


def test_require_admin_missing_header_returns_401():
    request = _mock_request(_admin_settings("real-admin-key"), None)
    with pytest.raises(HTTPException) as exc_info:
        _require_admin(request, None)
    assert exc_info.value.status_code == 401


def test_require_admin_correct_key_passes():
    request = _mock_request(_admin_settings("real-admin-key"), "Bearer real-admin-key")
    assert _require_admin(request, None) is None


# ---------------------------------------------------------------------------
# LL2 pagination next-URL validation
# ---------------------------------------------------------------------------


def _ll2_client() -> LL2Client:
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        ll2_base_url="https://ll.thespacedevs.example/2.3.0",
    )
    return LL2Client(settings, client=MagicMock())


def test_ll2_next_url_none_passes_through():
    assert _ll2_client()._validate_next_url(None) is None


def test_ll2_next_url_same_host_allowed():
    url = "https://ll.thespacedevs.example/2.3.0/launches/upcoming/?offset=100"
    assert _ll2_client()._validate_next_url(url) == url


def test_ll2_next_url_off_host_rejected():
    with pytest.raises(LL2ClientError) as exc_info:
        _ll2_client()._validate_next_url("https://evil.example/steal-token")
    assert exc_info.value.code == "LL2_INVALID_NEXT_URL"


def test_ll2_next_url_scheme_downgrade_rejected():
    with pytest.raises(LL2ClientError) as exc_info:
        _ll2_client()._validate_next_url("http://ll.thespacedevs.example/2.3.0/x")
    assert exc_info.value.code == "LL2_INVALID_NEXT_URL"


def test_ll2_next_url_non_string_rejected():
    with pytest.raises(LL2ClientError) as exc_info:
        _ll2_client()._validate_next_url({"url": "https://ll.thespacedevs.example/x"})
    assert exc_info.value.code == "LL2_INVALID_NEXT_URL"


# ---------------------------------------------------------------------------
# Upstream URL sanitisation before storage
# ---------------------------------------------------------------------------


def test_apod_payload_urls_sanitised():
    row = _apod_from_payload(
        {
            "date": "2026-01-01",
            "title": "T",
            "explanation": "E",
            "url": "javascript:alert(1)",
            "hdurl": "data:text/html,<script>x</script>",
            "thumbnail_url": "https://apod.nasa.gov/thumb.jpg",
            "media_type": "image",
        },
        "2026-01-01",
    )
    assert row.url == ""
    assert row.hdurl is None
    assert row.thumbnail_url == "https://apod.nasa.gov/thumb.jpg"


def test_launch_parse_raw_sanitises_urls():
    fields = _parse_raw(
        {
            "id": "l-1",
            "name": "N",
            "net": "2026-07-10T12:00:00Z",
            "image": "javascript:alert(1)",
            "vidURLs": [
                {"title": "bad", "url": "javascript:alert(1)", "feature_image": ""},
                {
                    "title": "good",
                    "url": "https://youtube.example/watch?v=1",
                    "feature_image": "data:image/svg+xml,<svg onload=alert(1)>",
                },
            ],
        }
    )
    assert fields["image_url"] is None
    livestreams = fields["livestream_urls"]
    assert len(livestreams) == 1
    assert all("javascript:" not in item["url"] for item in livestreams)
    assert all("data:" not in item["feature_image"] for item in livestreams)
    assert livestreams[0]["url"] == "https://youtube.example/watch?v=1"


def test_launch_parse_raw_image_object_form_sanitised():
    fields = _parse_raw(
        {
            "id": "l-2",
            "name": "N",
            "net": "2026-07-10T12:00:00Z",
            "image": {"image_url": "javascript:alert(1)", "thumbnail_url": None},
        }
    )
    assert fields["image_url"] is None


def test_mars_photo_img_src_sanitised():
    row = _row_from_photo(
        {
            "id": 7,
            "sol": 100,
            "earth_date": "2026-01-01",
            "camera": {"name": "NAVCAM"},
            "rover": {"name": "Perseverance"},
            "img_src": "javascript:alert(1)",
        }
    )
    assert row is not None
    assert row.img_src == ""


def test_neo_jpl_url_sanitised():
    neo = _neo_from_object(
        {"id": "123", "name": "Apophis", "nasa_jpl_url": "javascript:alert(1)"},
        "2026-01-01",
    )
    assert neo.nasa_jpl_url is None

    neo_ok = _neo_from_object(
        {"id": "124", "name": "Bennu", "nasa_jpl_url": "https://ssd.jpl.nasa.gov/x"},
        "2026-01-01",
    )
    assert neo_ok.nasa_jpl_url == "https://ssd.jpl.nasa.gov/x"


# ---------------------------------------------------------------------------
# Registration input limits
# ---------------------------------------------------------------------------


def _register_kwargs(**overrides):
    base = {
        "first_name": "Alice",
        "last_name": "Liddell",
        "email": "alice@example.com",
        "password": "securepassword",
    }
    base.update(overrides)
    return base


def test_register_rejects_email_without_at():
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(email="not-an-email"))


def test_register_rejects_email_with_multiple_ats():
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(email="a@b@c.com"))


def test_register_rejects_overlong_names():
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(first_name="x" * 101))
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(last_name=""))


def test_register_rejects_password_over_72_bytes():
    # 72-byte limit is a byte limit: multi-byte characters count fully
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(password="p" * 73))
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(password="ü" * 40))  # 80 bytes


def test_register_accepts_boundary_password():
    req = RegisterRequest(**_register_kwargs(password="p" * 72))
    assert len(req.password) == 72


def test_register_rejects_overlong_email_and_phone():
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(email="a" * 250 + "@example.com"))
    with pytest.raises(ValidationError):
        RegisterRequest(**_register_kwargs(phone="+1" + "5" * 40))


# ---------------------------------------------------------------------------
# OTP codes must not reach production logs
# ---------------------------------------------------------------------------


def _prod_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=True,
        jwt_secret_key="test-jwt-secret-that-is-long-enough",
        unsubscribe_secret_key="test-unsub-secret-that-is-long-enough",
        admin_api_key="test-admin-key-that-is-long-enough",
    )


async def test_register_does_not_log_otp_in_production(db_session, caplog):
    settings = _prod_settings()
    with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
        user = await auth_service.register_user(
            db_session,
            {
                "first_name": "Prod",
                "last_name": "User",
                "email": "prod@example.com",
                "password": "securepassword",
            },
            settings,
        )
    otp_lines = [r.message for r in caplog.records if "OTP" in r.message]
    assert otp_lines, "expected an OTP stub log line"
    for line in otp_lines:
        assert str(user.id) in line
        # No 6-digit code anywhere in the message
        assert not any(
            part.isdigit() and len(part) == 6 for part in line.replace(":", " ").split()
        )


async def test_register_logs_otp_in_dev(db_session, caplog, settings):
    with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
        await auth_service.register_user(
            db_session,
            {
                "first_name": "Dev",
                "last_name": "User",
                "email": "dev@example.com",
                "password": "securepassword",
            },
            settings,
        )
    otp_lines = [r.message for r in caplog.records if "OTP for user" in r.message]
    assert otp_lines, "dev stub should log the OTP code"


async def test_resend_does_not_log_otp_in_production(db_session, caplog):
    settings = _prod_settings()
    user = await auth_service.register_user(
        db_session,
        {
            "first_name": "Prod2",
            "last_name": "User",
            "email": "prod2@example.com",
            "password": "securepassword",
        },
        settings,
    )
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.services.auth_service"):
        await auth_service.resend_otp(db_session, user.id, "email", settings)
    otp_lines = [r.message for r in caplog.records if "OTP" in r.message]
    assert otp_lines
    for line in otp_lines:
        assert not any(
            part.isdigit() and len(part) == 6 for part in line.replace(":", " ").split()
        )
