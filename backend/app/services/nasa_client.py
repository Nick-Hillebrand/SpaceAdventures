"""Shared httpx client for NASA API calls with structured error branches.

Per Architecture/03-caching-strategy.md and Architecture/02-api-routes.md, the
following error codes are surfaced to callers via ``NasaClientError``:

- ``NO_INTERNET`` — connectivity probe failed
- ``NASA_UNAVAILABLE`` — network reached the public internet but NASA is
  unreachable (connection error) or returned 5xx
- ``NASA_AUTH_ERROR`` — NASA returned 401/403
- ``NASA_ERROR`` — NASA returned some other non-2xx status
- ``INTERNAL_ERROR`` — anything unexpected

The client is a lifespan-scoped singleton (P6) — do not construct a new
``httpx.AsyncClient`` per request.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


class NasaClientError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NasaClient:
    """Async NASA API client that owns a shared httpx.AsyncClient."""

    _CONNECTIVITY_URL = "https://www.google.com"
    _CONNECTIVITY_TIMEOUT = 3.0

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.nasa_base_url,
            timeout=settings.http_timeout_seconds,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        treat_404_as_unavailable: bool = False,
    ) -> Any:
        """GET a NASA endpoint and return parsed JSON.

        Raises ``NasaClientError`` with a structured error code on failure.

        ``treat_404_as_unavailable`` is for endpoints where the caller already
        validates all inputs that could legitimately produce a 404, so any 404
        actually observed means the upstream route itself is gone (e.g. the
        mars-photos API's Heroku backend returning its "no such app" page)
        rather than a normal not-found response.
        """
        query = {"api_key": self._settings.nasa_api_key}
        if params:
            query.update({k: v for k, v in params.items() if v is not None})

        try:
            response = await self._client.get(path, params=query)
        except httpx.ConnectError:
            code = await self._classify_connect_error()
            raise NasaClientError(code, "NASA client could not reach upstream")
        except httpx.HTTPError as exc:  # timeouts, read errors, etc.
            raise NasaClientError("NASA_UNAVAILABLE", f"NASA HTTP error: {type(exc).__name__}")

        if response.status_code in (401, 403):
            raise NasaClientError("NASA_AUTH_ERROR", "NASA rejected the API key")
        if response.status_code == 404 and treat_404_as_unavailable:
            raise NasaClientError("NASA_UNAVAILABLE", "NASA returned 404 (endpoint unavailable)")
        if response.status_code >= 500:
            raise NasaClientError("NASA_UNAVAILABLE", f"NASA returned {response.status_code}")
        if response.status_code >= 400:
            raise NasaClientError("NASA_ERROR", f"NASA returned {response.status_code}")

        try:
            return response.json()
        except ValueError as exc:
            raise NasaClientError("NASA_ERROR", f"NASA returned invalid JSON: {exc}")

    async def _classify_connect_error(self) -> str:
        """Send a HEAD probe to google.com to distinguish NO_INTERNET vs NASA_UNAVAILABLE."""
        try:
            async with httpx.AsyncClient(timeout=self._CONNECTIVITY_TIMEOUT) as probe:
                await probe.head(self._CONNECTIVITY_URL)
        except httpx.HTTPError:
            return "NO_INTERNET"
        return "NASA_UNAVAILABLE"
