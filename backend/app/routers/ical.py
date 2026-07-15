"""iCal feed router (Architecture/19-notification-channels-v2.md L2).

GET  /api/v1/ical/{token}.ics  — capability-URL auth: the token IS the auth.
POST /api/v1/ical/rotate       — auth-required, Pro-gated; generates/rotates the token.

The capability GET is public in the sense that it takes no Bearer header,
but the token itself gates access. No oracle: both "token unknown" and
"valid token belonging to a non-Pro user" return 404 — identical responses
prevent token-existence enumeration (25-security-testing.md §2.1).

POST /rotate requires both a valid Bearer token AND is_pro — the rotate action
is a Pro-scoped resource; free-tier users must not obtain an ical_token even
though the GET feed would 404 them anyway (CLAUDE.md rule 11).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user_dep
from app.services import ical_service

router = APIRouter(prefix="/api/v1/ical", tags=["ical"])


@router.get("/{token}.ics", response_class=Response)
async def get_ical_feed(
    token: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Return a VCALENDAR of the user's subscribed launches.

    Capability-URL auth: calendar apps cannot send Bearer headers, so the
    token IS the credential. An invalid token → 404 (no oracle — same as
    a nonexistent resource, 25-security-testing.md §2.1).
    """
    user = await ical_service.get_user_by_ical_token(session, token)
    if user is None or not user.is_pro:
        # No oracle: both "unknown token" and "valid token, non-Pro user" return 404.
        # This prevents enumeration of valid tokens via status-code differences.
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Feed not found"}})

    ics = await ical_service.build_calendar(session, user)
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=900"},
    )


@router.post("/rotate", status_code=200)
async def rotate_ical_token(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_dep),
) -> dict:
    """Generate or rotate the iCal feed token (Pro-gated).

    Rotation immediately invalidates the old webcal:// URL. The response
    contains the new raw token; the frontend constructs the webcal:// URL.
    """
    if not user.is_pro:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "PRO_REQUIRED", "message": "iCal feed requires a Pro subscription"}},
        )
    token = await ical_service.rotate_token(session, user)
    return {"ical_token": token}
