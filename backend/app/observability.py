"""Structured logging + error reporting baseline (17-worker-and-scheduling.md P3.6).

Shared by both the web process (`main.py`) and the worker process
(`worker.py`) so the two produce identical log shapes in production.
"""
from __future__ import annotations

import sys

import structlog

from app.config import Settings


def configure_logging() -> None:
    """JSON logging to stdout — request id, job name, duration are added by
    call sites via `structlog.contextvars` or explicit `logger.bind(...)`."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def init_sentry(settings: Settings, *, component: str) -> None:
    """Initialize the Sentry SDK when `SENTRY_DSN` is set. No-op otherwise
    (empty DSN is the default — Sentry must never be a hard dependency)."""
    if not settings.sentry_dsn:
        return

    import sentry_sdk  # noqa: PLC0415 — only imported when actually configured

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.05,
    )
    sentry_sdk.set_tag("component", component)


def capture_exception(exc: Exception) -> None:
    """Report `exc` to Sentry if it's configured; always safe to call."""
    import sentry_sdk  # noqa: PLC0415

    if sentry_sdk.is_initialized():
        sentry_sdk.capture_exception(exc)
