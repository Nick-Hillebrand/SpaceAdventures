"""Sky-location service — geocode proxy, store, clear (20-location-and-sky-alerts.md).

Location is server-validated PII: lat/lng are rounded to 2 decimals at write
time (a few blocks of precision — plenty for pass/aurora visibility, and it
keeps pass_precompute's per-coordinate N2YO-call batching effective across
users who share a city). Never trust a client-supplied lat/lng pair as
already-rounded or in-range; both are re-validated here regardless of what
the geocode search returned.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.location import LocationCandidate, SetLocationRequest
from app.services.geocode_client import GeocodeClient, GeocodeClientError
from app.services.notification_service import sanitise

MAX_CANDIDATES = 5


async def search_location(client: GeocodeClient, query: str) -> list[LocationCandidate]:
    """Proxy a location search through the geocoding client.

    Raises GeocodeClientError (caller maps it to an HTTP response) — the
    frontend never talks to Open-Meteo directly.
    """
    raw_results = await client.search(query, count=MAX_CANDIDATES)
    candidates: list[LocationCandidate] = []
    for r in raw_results[:MAX_CANDIDATES]:
        try:
            candidates.append(
                LocationCandidate(
                    # Open-Meteo is untrusted upstream input (10-security.md,
                    # CLAUDE.md rule 9) — strip control chars before it ever
                    # reaches the client or (if the user picks it) storage.
                    name=sanitise(str(r["name"])),
                    country=sanitise(str(r["country"])) if r.get("country") is not None else None,
                    admin1=sanitise(str(r["admin1"])) if r.get("admin1") is not None else None,
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    timezone=str(r.get("timezone") or "UTC"),
                )
            )
        except (KeyError, TypeError, ValueError):
            # Malformed candidate from upstream — skip it rather than fail
            # the whole search (schema-validate before storage, not before
            # display; a partial candidate list is still useful).
            continue
    return candidates


def _validate_coordinates(lat: float, lng: float) -> None:
    if not (-90 <= lat <= 90):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "latitude must be in [-90, 90]"}},
        )
    if not (-180 <= lng <= 180):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "longitude must be in [-180, 180]"}},
        )


async def set_location(
    session: AsyncSession, user: User, data: SetLocationRequest
) -> User:
    """Validate and persist a chosen location candidate on `user`."""
    _validate_coordinates(data.latitude, data.longitude)

    # `name` is client-supplied and not verified against an actual search
    # result — sanitise it directly rather than trusting the frontend to
    # only ever echo back an already-sanitised search_location() candidate.
    user.location_name = sanitise(data.name)
    user.location_lat = round(data.latitude, 2)
    user.location_lng = round(data.longitude, 2)
    user.location_tz = data.timezone
    await session.commit()
    await session.refresh(user)
    return user


async def clear_location(session: AsyncSession, user: User) -> User:
    """Null all four location columns on `user`."""
    user.location_name = None
    user.location_lat = None
    user.location_lng = None
    user.location_tz = None
    await session.commit()
    await session.refresh(user)
    return user


def geocode_error_response(exc: GeocodeClientError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": {"code": exc.code, "message": exc.message}},
    )
