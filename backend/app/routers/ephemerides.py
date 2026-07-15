from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.ephemerides import EphemeridesResponse, EphemerisPoint
from app.services import ephemerides_service
from app.services.ephemerides_service import UnknownSlugError

router = APIRouter(prefix="/api/v1/ephemerides", tags=["ephemerides"])

# Default window when `from`/`to` are omitted — matches the worker's past
# coverage so a caller with no opinion gets a fully-cached response.
_DEFAULT_RANGE_DAYS = 30


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@router.get("/{slug}", response_model=EphemeridesResponse)
async def get_ephemerides(
    slug: str,
    response: Response,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> EphemeridesResponse:
    now = datetime.now(timezone.utc)
    start = _as_utc(from_) if from_ is not None else now - timedelta(days=_DEFAULT_RANGE_DAYS)
    end = _as_utc(to) if to is not None else now

    try:
        result = await ephemerides_service.get_ephemerides(session, slug, start, end)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_RANGE", "message": str(exc)}},
        )
    except UnknownSlugError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "UNKNOWN_OBJECT",
                    "message": f"no tracked object with slug {slug!r}",
                }
            },
        )

    response.headers["Cache-Control"] = "public, max-age=3600"
    return EphemeridesResponse(
        slug=result.slug,
        name_key=result.name_key,
        points=[
            EphemerisPoint(t=point.t_utc, x=point.x_au, y=point.y_au, z=point.z_au)
            for point in result.points
        ],
    )
