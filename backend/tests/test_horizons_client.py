"""Direct unit tests of HorizonsClient/parse_vectors_csv for coverage of
error-branch internals not exercised via ephemerides_service
(22-ephemeris-and-mission-replay.md — Foundation)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.services.horizons_client import (
    HorizonsClient,
    HorizonsError,
    _jd_to_utc,
    parse_vectors_csv,
)

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"


def _client() -> HorizonsClient:
    return HorizonsClient(Settings(require_secrets=False))  # type: ignore[call-arg]


@pytest.fixture
async def horizons_client():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


def _sample_result(rows: str = "") -> str:
    body = rows or (
        "2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000, "
        "1.234567890123456E+00, 2.345678901234567E-01, -3.456789012345678E-02,\n"
    )
    return f"$$SOE\n{body}$$EOE\n"


# ---------------------------------------------------------------------------
# parse_vectors_csv
# ---------------------------------------------------------------------------


def test_parse_vectors_csv_happy_path():
    points = parse_vectors_csv(_sample_result())
    assert len(points) == 1
    t, x, y, z = points[0]
    assert t.tzinfo is not None
    assert x == pytest.approx(1.234567890123456)
    assert y == pytest.approx(0.2345678901234567)
    assert z == pytest.approx(-0.03456789012345678)


def test_parse_vectors_csv_skips_blank_lines_between_markers():
    rows = (
        "2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000, 1.0, 2.0, 3.0,\n"
        "\n"
        "2460310.541666667, A.D. 2024-Jan-01 01:00:00.0000, 1.1, 2.1, 3.1,\n"
    )
    points = parse_vectors_csv(_sample_result(rows))
    assert len(points) == 2


def test_parse_vectors_csv_missing_markers_raises_parse_error():
    with pytest.raises(HorizonsError) as exc:
        parse_vectors_csv("no markers here at all")
    assert exc.value.code == "HORIZONS_PARSE_ERROR"


def test_parse_vectors_csv_short_row_raises_parse_error():
    rows = "2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000, 1.0,\n"
    with pytest.raises(HorizonsError) as exc:
        parse_vectors_csv(_sample_result(rows))
    assert exc.value.code == "HORIZONS_PARSE_ERROR"


@pytest.mark.parametrize(
    "bad_field",
    [
        "<script>alert(1)</script>",
        "'; DROP TABLE ephemerides; --",
        "not-a-number",
        "",
    ],
)
def test_parse_vectors_csv_non_numeric_field_raises_parse_error(bad_field):
    """Horizons' response is untrusted upstream input (25-…§2.3/§2.5) — a
    non-numeric field (including injection-shaped strings) must raise
    HorizonsError rather than being coerced or silently stored."""
    rows = f"2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000, {bad_field}, 2.0, 3.0,\n"
    with pytest.raises(HorizonsError) as exc:
        parse_vectors_csv(_sample_result(rows))
    assert exc.value.code == "HORIZONS_PARSE_ERROR"


@pytest.mark.parametrize("bad_field", ["nan", "-nan", "inf", "-inf", "Infinity"])
def test_parse_vectors_csv_non_finite_field_raises_parse_error(bad_field):
    """`float()` accepts "nan"/"inf" spellings that `HORIZONS_PARSE_ERROR`'s
    sibling test above doesn't cover — these must be rejected too, since a
    stored NaN/Infinity would round-trip as an invalid JSON token."""
    rows = f"2460310.500000000, A.D. 2024-Jan-01 00:00:00.0000, {bad_field}, 2.0, 3.0,\n"
    with pytest.raises(HorizonsError) as exc:
        parse_vectors_csv(_sample_result(rows))
    assert exc.value.code == "HORIZONS_PARSE_ERROR"


# ---------------------------------------------------------------------------
# _jd_to_utc
# ---------------------------------------------------------------------------


def test_jd_to_utc_unix_epoch():
    assert _jd_to_utc(2440587.5) == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_jd_to_utc_rounds_subsecond_noise_to_nearest_second():
    # A JD offset by a floating-point hair over a whole-second boundary must
    # round to the same instant, not drift — otherwise two syncs of the same
    # sample would produce PK-distinct rows (see module docstring/P-note in
    # horizons_client.py).
    base = 2440587.5 + (3600 / 86400)  # exactly 1970-01-01T01:00:00Z
    noisy = base + 1e-10
    assert _jd_to_utc(noisy) == _jd_to_utc(base)


# ---------------------------------------------------------------------------
# HorizonsClient.fetch_vectors
# ---------------------------------------------------------------------------


@respx.mock
async def test_fetch_vectors_happy_path(horizons_client):
    respx.get(HORIZONS_URL).mock(
        return_value=httpx.Response(200, json={"result": _sample_result()})
    )
    points = await horizons_client.fetch_vectors(
        "-170",
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 2, tzinfo=timezone.utc),
        24,
    )
    assert len(points) == 1


@respx.mock
async def test_fetch_vectors_connect_error_maps_to_unavailable(horizons_client):
    respx.get(HORIZONS_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_UNAVAILABLE"


@respx.mock
async def test_fetch_vectors_read_timeout_maps_to_unavailable(horizons_client):
    respx.get(HORIZONS_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_UNAVAILABLE"


@respx.mock
async def test_fetch_vectors_http_error_status_maps_to_unavailable(horizons_client):
    respx.get(HORIZONS_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_UNAVAILABLE"


@respx.mock
async def test_fetch_vectors_invalid_json_maps_to_invalid_json(horizons_client):
    respx.get(HORIZONS_URL).mock(return_value=httpx.Response(200, content=b"not json"))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_INVALID_JSON"


@respx.mock
async def test_fetch_vectors_missing_result_field_raises_parse_error(horizons_client):
    respx.get(HORIZONS_URL).mock(return_value=httpx.Response(200, json={"not_result": "x"}))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_PARSE_ERROR"


@respx.mock
async def test_fetch_vectors_oversized_response_rejected(horizons_client):
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    respx.get(HORIZONS_URL).mock(return_value=httpx.Response(200, content=oversized))
    with pytest.raises(HorizonsError) as exc:
        await horizons_client.fetch_vectors(
            "-170",
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
            24,
        )
    assert exc.value.code == "HORIZONS_RESPONSE_TOO_LARGE"


@respx.mock
async def test_fetch_vectors_sends_expected_query_params(horizons_client):
    route = respx.get(HORIZONS_URL).mock(
        return_value=httpx.Response(200, json={"result": _sample_result()})
    )
    await horizons_client.fetch_vectors(
        "-170",
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 2, tzinfo=timezone.utc),
        24,
    )
    request = route.calls.last.request
    query = dict(httpx.QueryParams(request.url.query))
    assert query["COMMAND"] == "'-170'"
    assert query["EPHEM_TYPE"] == "VECTORS"
    assert query["CENTER"] == "'500@10'"
    assert query["STEP_SIZE"] == "'24h'"
    assert query["CSV_FORMAT"] == "'YES'"
