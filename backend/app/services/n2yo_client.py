"""N2YO API client.

Key rules (from Architecture/11-testing.md and 05-iss-tracker.md):

P4  - The asyncio.Lock must be defined at MODULE LEVEL, not inside a function.
P12 - N2YO returns HTTP 200 even on errors; always check body for {"error": ...}.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import Settings

# P4: module-level lock — never instantiate inside a function/method
_QUOTA_LOCK: asyncio.Lock = asyncio.Lock()

ISS_NORAD = 25544


class N2YOError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class N2YOClient:
    """Async N2YO API client that owns a shared httpx.AsyncClient."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.n2yo_base_url,
            timeout=settings.http_timeout_seconds,
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str) -> Any:
        """GET a N2YO endpoint and return parsed JSON.

        Raises N2YOError on any failure, including HTTP-200-with-error-body (P12).
        """
        try:
            response = await self._client.get(
                path,
                params={"apiKey": self._settings.n2yo_api_key},
            )
        except httpx.ConnectError:
            raise N2YOError("N2YO_UNAVAILABLE", "N2YO API unreachable")
        except httpx.HTTPError as exc:
            raise N2YOError("N2YO_UNAVAILABLE", f"N2YO HTTP error: {type(exc).__name__}")

        if response.status_code >= 400:
            raise N2YOError("N2YO_UNAVAILABLE", f"N2YO returned {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise N2YOError("N2YO_ERROR", f"N2YO returned invalid JSON: {exc}")

        # P12: N2YO returns HTTP 200 even on errors
        if isinstance(data, dict) and "error" in data:
            raise N2YOError("N2YO_ERROR", str(data["error"]))

        return data

    async def get_positions(self, lat: float = 0.0, lng: float = 0.0, alt: float = 0.0, seconds: int = 300) -> Any:
        return await self._get(f"positions/{ISS_NORAD}/{lat}/{lng}/{alt}/{seconds}")

    async def get_tle(self) -> Any:
        return await self._get(f"tle/{ISS_NORAD}")

    async def get_visual_passes(
        self, lat: float, lng: float, alt: float, days: int = 7, min_visibility: int = 10
    ) -> Any:
        return await self._get(
            f"visualpasses/{ISS_NORAD}/{lat}/{lng}/{alt}/{days}/{min_visibility}"
        )

    async def get_radio_passes(self, lat: float, lng: float, alt: float) -> Any:
        return await self._get(f"radiopasses/{ISS_NORAD}/{lat}/{lng}/{alt}/7/10")
