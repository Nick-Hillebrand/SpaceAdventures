"""Client for NASA's public mars.nasa.gov raw-image galleries.

api.nasa.gov/mars-photos (the old `corincerami/mars-photo-api` Heroku app) has
been permanently decommissioned — every route under it now 404s. These are the
live, free, key-less endpoints that power NASA's own public raw-image browsers
and replace it for the two rovers that still have a working live source:

- Curiosity (MSL): ``https://mars.nasa.gov/api/v1/raw_image_items/``
- Perseverance (Mars2020): ``https://mars.nasa.gov/rss/api/?feed=raw_images``

Opportunity and Spirit (MER) have no live source anywhere on NASA's current
infrastructure — their imagery only ever lived behind the now-dead Heroku
mirror. Callers should serve cached rows for those rovers and otherwise report
unavailability without calling this client (see mars_service.LIVE_ROVERS).

Neither endpoint reliably supports server-side earth_date filtering, so
earth_date queries are approximated: estimate the sol from each rover's
landing date and the Mars sol length, fetch sol-1/sol/sol+1 as candidates,
then filter the (accurate) per-item earth_date client-side.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings
from app.services.nasa_client import NasaClientError

MSL_BASE = "https://mars.nasa.gov/api/v1/raw_image_items/"
M20_BASE = "https://mars.nasa.gov/rss/api/"

MSL_LANDING = datetime(2012, 8, 6, 5, 17, 57, tzinfo=timezone.utc)
M20_LANDING = datetime(2021, 2, 18, 20, 55, 0, tzinfo=timezone.utc)
SOL_SECONDS = 88775.244

_MSL_PER_PAGE = 100
_MSL_MAX_PAGES = 5  # caps a single-sol fetch at 500 photos

# Curiosity's raw-images API reports granular left/right/A-side/B-side
# instrument codes; the app's UI (and ROVER_CAMERAS) only exposes the
# simplified categories the old mars-photos API used.
MSL_CAMERA_MAP: dict[str, str] = {
    "FHAZ_LEFT_A": "FHAZ", "FHAZ_LEFT_B": "FHAZ", "FHAZ_RIGHT_A": "FHAZ", "FHAZ_RIGHT_B": "FHAZ",
    "RHAZ_LEFT_A": "RHAZ", "RHAZ_LEFT_B": "RHAZ", "RHAZ_RIGHT_A": "RHAZ", "RHAZ_RIGHT_B": "RHAZ",
    "NAV_LEFT_A": "NAVCAM", "NAV_LEFT_B": "NAVCAM", "NAV_RIGHT_A": "NAVCAM", "NAV_RIGHT_B": "NAVCAM",
    "MAST_LEFT": "MAST", "MAST_RIGHT": "MAST",
    "CHEMCAM_RMI": "CHEMCAM",
    "MAHLI": "MAHLI",
    "MARDI": "MARDI",
}


def normalize_msl_camera(instrument: str) -> str:
    return MSL_CAMERA_MAP.get(instrument.upper(), instrument.upper())


def sol_estimate(earth_date: str, landing: datetime) -> int:
    dt = datetime.fromisoformat(earth_date).replace(tzinfo=timezone.utc)
    return max(0, int((dt - landing).total_seconds() // SOL_SECONDS))


def sol_candidates(earth_date: str, landing: datetime) -> list[int]:
    estimate = sol_estimate(earth_date, landing)
    return sorted({max(0, estimate - 1), estimate, estimate + 1})


def synthetic_id(image_id: str) -> int:
    """Stable positive 63-bit id for M20 photos, which have no numeric id.

    SHA-256 truncated to 8 bytes; at ~1M images the collision probability is
    negligible (unlike 32-bit CRC32, which was rejected for this reason).
    """
    digest = hashlib.sha256(image_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


class MarsRawImagesClient:
    """Async client that owns a shared httpx.AsyncClient for mars.nasa.gov."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.get(url, params=params)
        except httpx.ConnectError as exc:
            raise NasaClientError(
                "MARS_ARCHIVE_UNAVAILABLE", f"Could not reach mars.nasa.gov: {exc}"
            )
        except httpx.HTTPError as exc:
            raise NasaClientError(
                "MARS_ARCHIVE_UNAVAILABLE", f"mars.nasa.gov HTTP error: {type(exc).__name__}"
            )

        if response.status_code >= 400:
            raise NasaClientError(
                "MARS_ARCHIVE_UNAVAILABLE", f"mars.nasa.gov returned {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise NasaClientError(
                "MARS_ARCHIVE_UNAVAILABLE", f"mars.nasa.gov returned invalid JSON: {exc}"
            )

    async def fetch_msl_photos(
        self, *, sol: int | None = None, earth_date: str | None = None
    ) -> list[dict[str, Any]]:
        sols = [sol] if sol is not None else sol_candidates(earth_date, MSL_LANDING)  # type: ignore[arg-type]
        photos: list[dict[str, Any]] = []
        for candidate_sol in sols:
            photos.extend(await self._fetch_msl_sol(candidate_sol))
        if earth_date is not None:
            photos = [p for p in photos if p["earth_date"] == earth_date]
        return photos

    async def _fetch_msl_sol(self, sol: int) -> list[dict[str, Any]]:
        photos: list[dict[str, Any]] = []
        page = 0
        while page < _MSL_MAX_PAGES:
            payload = await self._get(
                MSL_BASE,
                {
                    "order": "sol desc",
                    "per_page": _MSL_PER_PAGE,
                    "page": page,
                    "condition_1": "msl:mission",
                    "condition_2": f"{sol}:sol:eq",
                },
            )
            items = payload.get("items") or []
            for item in items:
                date_taken = str(item.get("date_taken") or "")
                photos.append(
                    {
                        "id": item.get("id"),
                        "sol": item.get("sol"),
                        "earth_date": date_taken[:10],
                        "camera": {"name": normalize_msl_camera(str(item.get("instrument", "")))},
                        "rover": {"name": "Curiosity"},
                        "img_src": str(item.get("https_url") or item.get("url") or ""),
                    }
                )
            if not payload.get("more"):
                break
            page += 1
        return photos

    async def fetch_m20_photos(
        self, *, sol: int | None = None, earth_date: str | None = None
    ) -> list[dict[str, Any]]:
        sols = [sol] if sol is not None else sol_candidates(earth_date, M20_LANDING)  # type: ignore[arg-type]
        photos: list[dict[str, Any]] = []
        for candidate_sol in sols:
            photos.extend(await self._fetch_m20_sol(candidate_sol))
        if earth_date is not None:
            photos = [p for p in photos if p["earth_date"] == earth_date]
        return photos

    async def _fetch_m20_sol(self, sol: int) -> list[dict[str, Any]]:
        payload = await self._get(
            M20_BASE,
            {
                "feed": "raw_images",
                "category": "mars2020,ingenuity",
                "feedtype": "json",
                "ver": "1.2",
                "sol": sol,
            },
        )
        photos: list[dict[str, Any]] = []
        for image in payload.get("images") or []:
            image_id = str(image.get("imageid") or "")
            if not image_id:
                continue
            date_taken = str(image.get("date_taken_utc") or image.get("date_taken") or "")
            files = image.get("image_files") or {}
            img_src = str(files.get("full_res") or files.get("large") or files.get("medium") or "")
            camera = str((image.get("camera") or {}).get("instrument", "")).upper()
            photos.append(
                {
                    "id": synthetic_id(image_id),
                    "sol": image.get("sol"),
                    "earth_date": date_taken[:10],
                    "camera": {"name": camera},
                    "rover": {"name": "Perseverance"},
                    "img_src": img_src,
                }
            )
        return photos
