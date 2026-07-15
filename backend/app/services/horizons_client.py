"""JPL Horizons API client (Architecture/22-ephemeris-and-mission-replay.md
— Foundation).

Courtesy rules are hard requirements: batch queries, cache for days, NEVER
proxy a user request to JPL — the only caller of this client is the
`ephemeris_sync` worker job (`app/jobs.py`), never a request handler.

The client is a lifespan-scoped singleton (P6) — do not construct a new
``httpx.AsyncClient`` per request.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB

# Julian Date of the Unix epoch (1970-01-01T00:00:00Z) — used to convert
# Horizons' JDTDB column to an aware UTC datetime without a calendar-string
# parser. This ignores the (sub-second, at our 24h sampling density)
# TDB/UTC leap-second offset, which is negligible for a trajectory cache.
_UNIX_EPOCH_JD = 2440587.5


class HorizonsError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _jd_to_utc(jd: float) -> datetime:
    # Rounded to the nearest second: samples fall on whole step_hours
    # boundaries, so sub-second float noise from the JD conversion would
    # otherwise make two syncs of the same instant compare unequal.
    seconds = round((jd - _UNIX_EPOCH_JD) * 86400)
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


def parse_vectors_csv(result_text: str) -> list[tuple[datetime, float, float, float]]:
    """Parse a Horizons VECTORS/CSV_FORMAT=YES `result` text block.

    Expected row shape between ``$$SOE``/``$$EOE`` (VEC_TABLE='1'):
    ``JDTDB, Calendar Date, X, Y, Z,`` (trailing comma). Raises
    ``HorizonsError`` on any malformed row rather than propagating an
    unhandled exception — Horizons' response body is untrusted upstream
    input (25-security-testing.md §2.5).
    """
    lines = result_text.splitlines()
    try:
        start = lines.index("$$SOE") + 1
        end = lines.index("$$EOE")
    except ValueError as exc:
        raise HorizonsError(
            "HORIZONS_PARSE_ERROR", f"missing $$SOE/$$EOE markers: {exc}"
        )

    points: list[tuple[datetime, float, float, float]] = []
    for raw_line in lines[start:end]:
        line = raw_line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) < 5:
            raise HorizonsError(
                "HORIZONS_PARSE_ERROR", f"unexpected row shape: {raw_line!r}"
            )
        try:
            jd = float(fields[0])
            x = float(fields[2])
            y = float(fields[3])
            z = float(fields[4])
        except ValueError as exc:
            raise HorizonsError(
                "HORIZONS_PARSE_ERROR", f"non-numeric field in row {raw_line!r}: {exc}"
            )
        if not (math.isfinite(jd) and math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            raise HorizonsError(
                "HORIZONS_PARSE_ERROR", f"non-finite field in row {raw_line!r}"
            )
        points.append((_jd_to_utc(jd), x, y, z))
    return points


class HorizonsClient:
    """Async JPL Horizons API client that owns a shared httpx.AsyncClient."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_vectors(
        self,
        spk_id: str,
        start: datetime,
        stop: datetime,
        step_hours: int,
    ) -> list[tuple[datetime, float, float, float]]:
        """Fetch heliocentric-ecliptic-J2000 position vectors for one object
        over one time range. One call per (object, range) — the caller
        (`ephemeris_sync`) is responsible for coalescing missing coverage
        into the fewest possible calls (courtesy rules).
        """
        params: dict[str, Any] = {
            "format": "json",
            "COMMAND": f"'{spk_id}'",
            "EPHEM_TYPE": "VECTORS",
            "CENTER": "'500@10'",
            "START_TIME": start.strftime("'%Y-%m-%d %H:%M'"),
            "STOP_TIME": stop.strftime("'%Y-%m-%d %H:%M'"),
            "STEP_SIZE": f"'{step_hours}h'",
            "VEC_TABLE": "'1'",
            "OUT_UNITS": "'AU-D'",
            "CSV_FORMAT": "'YES'",
        }

        try:
            response = await self._client.get(self._settings.horizons_base_url, params=params)
        except httpx.ConnectError as exc:
            raise HorizonsError("HORIZONS_UNAVAILABLE", f"Horizons connection error: {exc}")
        except httpx.HTTPError as exc:
            raise HorizonsError(
                "HORIZONS_UNAVAILABLE", f"Horizons HTTP error: {type(exc).__name__}"
            )

        if len(response.content) > _MAX_RESPONSE_BYTES:
            raise HorizonsError(
                "HORIZONS_RESPONSE_TOO_LARGE",
                f"Horizons response exceeded {_MAX_RESPONSE_BYTES} bytes",
            )

        if response.status_code >= 400:
            raise HorizonsError(
                "HORIZONS_UNAVAILABLE", f"Horizons returned HTTP {response.status_code}"
            )

        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise HorizonsError("HORIZONS_INVALID_JSON", f"Horizons returned invalid JSON: {exc}")

        result = data.get("result")
        if not isinstance(result, str):
            raise HorizonsError(
                "HORIZONS_PARSE_ERROR", "Horizons response is missing a 'result' text field"
            )

        return parse_vectors_csv(result)
