"""Open-Meteo geocoding API client (20-location-and-sky-alerts.md — Foundation).

Free, no API key. Structured error codes mirror `nasa_client.py`:

- ``GEOCODE_UNAVAILABLE`` — network reached the public internet but
  Open-Meteo is unreachable (connection error) or returned 5xx
- ``GEOCODE_NO_RESULT`` — Open-Meteo returned zero candidates for the query
- ``GEOCODE_ERROR`` — Open-Meteo returned some other non-2xx status or
  malformed JSON

The frontend never calls Open-Meteo directly — every request is proxied
through this client so upstream response shape/size never reaches the
browser unvalidated (25-security-testing.md §2.5).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings

# 25-security-testing.md §2.5 — cap upstream response size before parsing.
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class GeocodeClientError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class GeocodeClient:
    """Async Open-Meteo geocoding client that owns a shared httpx.AsyncClient."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.geocode_base_url,
            timeout=settings.http_timeout_seconds,
            follow_redirects=False,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, count: int = 5) -> list[dict[str, Any]]:
        """Return up to `count` geocoding candidates for `query`.

        Raises GeocodeClientError on any failure, including a well-formed
        empty result set (GEOCODE_NO_RESULT).
        """
        try:
            response = await self._client.get(
                "/v1/search",
                params={"name": query, "count": count, "language": "en", "format": "json"},
            )
        except httpx.ConnectError:
            raise GeocodeClientError("GEOCODE_UNAVAILABLE", "Geocoding service unreachable")
        except httpx.HTTPError as exc:
            raise GeocodeClientError(
                "GEOCODE_UNAVAILABLE", f"Geocoding HTTP error: {type(exc).__name__}"
            )

        if response.status_code >= 500:
            raise GeocodeClientError(
                "GEOCODE_UNAVAILABLE", f"Geocoding service returned {response.status_code}"
            )
        if response.status_code >= 400:
            raise GeocodeClientError(
                "GEOCODE_ERROR", f"Geocoding service returned {response.status_code}"
            )

        content_length = response.headers.get("content-length")
        if content_length is not None and int(content_length) > _MAX_RESPONSE_BYTES:
            raise GeocodeClientError("GEOCODE_ERROR", "Geocoding response exceeded size limit")
        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise GeocodeClientError("GEOCODE_ERROR", "Geocoding response exceeded size limit")

        try:
            data = response.json()
        except ValueError as exc:
            raise GeocodeClientError("GEOCODE_ERROR", f"Geocoding returned invalid JSON: {exc}")

        results = data.get("results") if isinstance(data, dict) else None
        if not results:
            raise GeocodeClientError("GEOCODE_NO_RESULT", "No matching location found", 404)

        return results
