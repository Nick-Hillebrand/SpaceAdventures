"""Mars Rover Photos caching service.

Permanent cache keyed on (rover, sol, camera, page):
  - Cache hit → return without upstream call.
  - Today's earth_date in results → always re-fetch (upsert).
  - Upstream failure with cached rows → stale=True.
  - No cache + upstream failure → propagate NasaClientError.

earth_date is stored as-is; the 'today' check is done per returned photo
because a given (rover, sol) can only appear on one earth_date which is fixed
once observed. We re-fetch only when the earth_date is today in UTC, treating
the sol/date mapping as potentially incomplete until tomorrow.

Only Curiosity and Perseverance have a live photo source (NASA's own
mars.nasa.gov raw-image galleries — see mars_raw_images_client). Opportunity
and Spirit have no live source anywhere on NASA's current infrastructure since
the old api.nasa.gov/mars-photos backend was decommissioned; they serve cached
rows only and otherwise raise MARS_NO_LIVE_SOURCE.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarsPhoto
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.nasa_client import NasaClientError

ROVERS = ("curiosity", "opportunity", "spirit", "perseverance")

# Rovers with a live photo source. Opportunity/Spirit are intentionally
# excluded — see module docstring.
LIVE_ROVERS = frozenset({"curiosity", "perseverance"})

# Cameras available per rover (used for the /rovers endpoint)
ROVER_CAMERAS: dict[str, list[str]] = {
    "curiosity": ["FHAZ", "RHAZ", "MAST", "CHEMCAM", "MAHLI", "MARDI", "NAVCAM"],
    "opportunity": ["FHAZ", "RHAZ", "NAVCAM", "PANCAM", "MINITES"],
    "spirit": ["FHAZ", "RHAZ", "NAVCAM", "PANCAM", "MINITES"],
    "perseverance": ["EDL_RUCAM", "EDL_RDCAM", "EDL_DDCAM", "EDL_PUCAM1", "EDL_PUCAM2",
                     "NAVCAM_LEFT", "NAVCAM_RIGHT", "MCZ_RIGHT", "MCZ_LEFT",
                     "FRONT_HAZCAM_LEFT_A", "FRONT_HAZCAM_RIGHT_A",
                     "REAR_HAZCAM_LEFT", "REAR_HAZCAM_RIGHT",
                     "SKYCAM", "SHERLOC_WATSON", "SUPERCAM_RMI"],
}

RoverName = Literal["curiosity", "opportunity", "spirit", "perseverance"]


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _row_from_photo(obj: dict) -> MarsPhoto | None:
    photo_id = obj.get("id")
    if photo_id is None:
        return None
    camera = obj.get("camera") or {}
    rover = obj.get("rover") or {}
    return MarsPhoto(
        id=int(photo_id),
        sol=int(obj.get("sol", 0)),
        earth_date=str(obj.get("earth_date", "")),
        rover_name=str(rover.get("name", "")).lower(),
        camera_name=str(camera.get("name", "")),
        img_src=str(obj.get("img_src", "")),
        fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


async def _upsert_photos(session: AsyncSession, photos: list[dict]) -> None:
    for obj in photos:
        row = _row_from_photo(obj)
        if row is None:
            continue
        existing = await session.get(MarsPhoto, row.id)
        if existing is None:
            session.add(row)
        else:
            existing.sol = row.sol
            existing.earth_date = row.earth_date
            existing.rover_name = row.rover_name
            existing.camera_name = row.camera_name
            existing.img_src = row.img_src
            existing.fetched_at = row.fetched_at
    await session.commit()


async def _query_photos(
    session: AsyncSession,
    rover: str,
    *,
    sol: int | None,
    earth_date: str | None,
    camera: str | None,
    page: int,
) -> list[MarsPhoto]:
    per_page = 25
    stmt = select(MarsPhoto).where(MarsPhoto.rover_name == rover.lower())
    if sol is not None:
        stmt = stmt.where(MarsPhoto.sol == sol)
    if earth_date is not None:
        stmt = stmt.where(MarsPhoto.earth_date == earth_date)
    if camera:
        stmt = stmt.where(MarsPhoto.camera_name == camera.upper())
    stmt = stmt.order_by(MarsPhoto.id).offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _is_today_result(rows: list[MarsPhoto]) -> bool:
    today = _today_utc()
    return any(r.earth_date == today for r in rows)


def _latest_fetched_at(rows: list[MarsPhoto]) -> datetime:
    if not rows:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return max(r.fetched_at for r in rows)


class MarsResult:
    def __init__(
        self,
        rows: list[MarsPhoto],
        cached: bool,
        stale: bool,
        is_today: bool,
        fetched_at: datetime,
    ) -> None:
        self.rows = rows
        self.cached = cached
        self.stale = stale
        self.is_today = is_today
        self.fetched_at = fetched_at


async def _fetch_live_photos(
    client: MarsRawImagesClient,
    rover: str,
    *,
    sol: int | None,
    earth_date: str | None,
    camera: str | None,
) -> list[dict]:
    if rover == "curiosity":
        photos = await client.fetch_msl_photos(sol=sol, earth_date=earth_date)
    else:
        photos = await client.fetch_m20_photos(sol=sol, earth_date=earth_date)
    if camera:
        photos = [p for p in photos if p["camera"]["name"].upper() == camera.upper()]
    return photos


async def fetch_photos(
    session: AsyncSession,
    client: MarsRawImagesClient,
    rover: str,
    *,
    sol: int | None = None,
    earth_date: str | None = None,
    camera: str | None = None,
    page: int = 1,
) -> MarsResult:
    """Return photos for a rover, applying permanent cache."""
    rover_lower = rover.lower()
    if rover_lower not in ROVERS:
        raise ValueError(f"Unknown rover '{rover}'")
    if sol is None and earth_date is None:
        raise ValueError("Either sol or earth_date must be provided")

    existing = await _query_photos(
        session, rover_lower, sol=sol, earth_date=earth_date, camera=camera, page=page
    )

    if rover_lower not in LIVE_ROVERS:
        if existing:
            return MarsResult(
                rows=existing,
                cached=True,
                stale=False,
                is_today=_is_today_result(existing),
                fetched_at=_latest_fetched_at(existing),
            )
        raise NasaClientError(
            "MARS_NO_LIVE_SOURCE",
            f"No live photo source is available for {rover_lower}: NASA's "
            "mars-photos API backend has been decommissioned and this rover "
            "has no replacement archive.",
        )

    is_today = _is_today_result(existing) if existing else (earth_date == _today_utc())
    if existing and not is_today:
        return MarsResult(
            rows=existing,
            cached=True,
            stale=False,
            is_today=False,
            fetched_at=_latest_fetched_at(existing),
        )

    try:
        photos = await _fetch_live_photos(
            client, rover_lower, sol=sol, earth_date=earth_date, camera=camera
        )
    except NasaClientError:
        if existing:
            return MarsResult(
                rows=existing,
                cached=True,
                stale=True,
                is_today=is_today,
                fetched_at=_latest_fetched_at(existing),
            )
        raise

    await _upsert_photos(session, photos)

    rows = await _query_photos(
        session, rover_lower, sol=sol, earth_date=earth_date, camera=camera, page=page
    )
    final_is_today = _is_today_result(rows) if rows else is_today
    return MarsResult(
        rows=rows,
        cached=False,
        stale=False,
        is_today=final_is_today,
        fetched_at=_latest_fetched_at(rows),
    )
