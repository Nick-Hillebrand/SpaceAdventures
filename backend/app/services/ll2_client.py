"""HTTP client for Launch Library 2 (LL2) API.

The client is a lifespan-scoped singleton — do not construct a new
httpx.AsyncClient per request.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


class LL2ClientError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class LL2Client:
    """Async LL2 API client that owns a shared httpx.AsyncClient."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        headers: dict[str, str] = {}
        if settings.ll2_api_key:
            headers["Authorization"] = f"Token {settings.ll2_api_key}"
        self._client = client or httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_upcoming(self) -> list[dict[str, Any]]:
        """Fetch all upcoming launches, paginating until next=None.

        Raises LL2ClientError on connection/timeout/non-200 errors or if a
        single page exceeds 5 MB.
        """
        launches: list[dict[str, Any]] = []
        url: str | None = (
            f"{self._settings.ll2_base_url}/launches/upcoming/"
            "?mode=detailed&limit=100&ordering=net"
        )
        while url:
            try:
                response = await self._client.get(url)
            except httpx.ConnectError as exc:
                raise LL2ClientError(
                    "LL2_UNAVAILABLE",
                    f"LL2 connection error: {exc}",
                )
            except httpx.TimeoutException as exc:
                raise LL2ClientError(
                    "LL2_TIMEOUT",
                    f"LL2 request timed out: {exc}",
                )
            except httpx.HTTPError as exc:
                raise LL2ClientError(
                    "LL2_HTTP_ERROR",
                    f"LL2 HTTP error: {type(exc).__name__}: {exc}",
                )

            if len(response.content) > _MAX_RESPONSE_BYTES:
                raise LL2ClientError(
                    "LL2_RESPONSE_TOO_LARGE",
                    f"LL2 response exceeded {_MAX_RESPONSE_BYTES} bytes",
                )

            if response.status_code != 200:
                raise LL2ClientError(
                    "LL2_ERROR",
                    f"LL2 returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )

            try:
                data: dict[str, Any] = response.json()
            except ValueError as exc:
                raise LL2ClientError(
                    "LL2_INVALID_JSON",
                    f"LL2 returned invalid JSON: {exc}",
                )

            launches.extend(data.get("results") or [])
            url = data.get("next")

        return launches
