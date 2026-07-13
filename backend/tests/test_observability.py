"""Tests for the structlog/Sentry observability baseline
(17-worker-and-scheduling.md P3.6)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app import observability
from app.config import Settings


def test_configure_logging_does_not_raise():
    observability.configure_logging()


def test_init_sentry_noop_without_dsn():
    settings = Settings(require_secrets=False, sentry_dsn="")  # type: ignore[call-arg]
    with patch("sentry_sdk.init") as mock_init:
        observability.init_sentry(settings, component="web")
    mock_init.assert_not_called()


def test_init_sentry_initializes_when_dsn_set():
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False, sentry_dsn="https://key@sentry.example/1"
    )
    with patch("sentry_sdk.init") as mock_init, patch("sentry_sdk.set_tag") as mock_tag:
        observability.init_sentry(settings, component="worker")
    mock_init.assert_called_once()
    assert mock_init.call_args.kwargs["dsn"] == "https://key@sentry.example/1"
    mock_tag.assert_called_once_with("component", "worker")


def test_capture_exception_noop_when_not_initialized():
    with patch("sentry_sdk.is_initialized", return_value=False), \
         patch("sentry_sdk.capture_exception") as mock_capture:
        observability.capture_exception(ValueError("boom"))
    mock_capture.assert_not_called()


def test_capture_exception_reports_when_initialized():
    exc = ValueError("boom")
    with patch("sentry_sdk.is_initialized", return_value=True), \
         patch("sentry_sdk.capture_exception") as mock_capture:
        observability.capture_exception(exc)
    mock_capture.assert_called_once_with(exc)
