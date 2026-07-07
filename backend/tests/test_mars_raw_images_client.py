"""Direct unit tests of MarsRawImagesClient for coverage of pagination and
error-branch internals not exercised via mars_service."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.services.mars_raw_images_client import (
    MSL_BASE,
    M20_BASE,
    MarsRawImagesClient,
    normalize_msl_camera,
    sol_candidates,
    synthetic_id,
)
from app.services.nasa_client import NasaClientError


def _client() -> MarsRawImagesClient:
    return MarsRawImagesClient(Settings(require_secrets=False))  # type: ignore[call-arg]


@pytest.fixture
async def mars_client():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


@respx.mock
async def test_msl_read_timeout_maps_to_unavailable(mars_client):
    respx.get(MSL_BASE).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(NasaClientError) as exc:
        await mars_client.fetch_msl_photos(sol=1)
    assert exc.value.code == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_msl_paginates_while_more_is_true(mars_client):
    def _page(page: int, more: bool) -> dict:
        return {
            "items": [
                {
                    "id": 1000 + page,
                    "sol": 1,
                    "date_taken": "2020-01-01T00:00:00Z",
                    "instrument": "MAHLI",
                    "https_url": f"https://mars.nasa.gov/{1000 + page}.jpg",
                }
            ],
            "more": more,
        }

    route = respx.get(MSL_BASE)
    route.side_effect = [
        httpx.Response(200, json=_page(0, True)),
        httpx.Response(200, json=_page(1, False)),
    ]
    photos = await mars_client.fetch_msl_photos(sol=1)
    assert len(photos) == 2
    assert route.call_count == 2


@respx.mock
async def test_msl_stops_at_max_pages(mars_client):
    route = respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": 1,
                        "sol": 1,
                        "date_taken": "2020-01-01T00:00:00Z",
                        "instrument": "MAHLI",
                        "https_url": "https://mars.nasa.gov/1.jpg",
                    }
                ],
                "more": True,
            },
        )
    )
    photos = await mars_client.fetch_msl_photos(sol=1)
    assert route.call_count == 5
    assert len(photos) == 5


@respx.mock
async def test_m20_skips_images_without_id(mars_client):
    respx.get(M20_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "images": [
                    {"sol": 1, "date_taken_utc": "2021-03-01T00:00:00Z", "camera": {"instrument": "NAVCAM_LEFT"}},
                    {
                        "imageid": "IMG1",
                        "sol": 1,
                        "date_taken_utc": "2021-03-01T00:00:00Z",
                        "camera": {"instrument": "NAVCAM_LEFT"},
                        "image_files": {"large": "https://mars.nasa.gov/img1.jpg"},
                    },
                ]
            },
        )
    )
    photos = await mars_client.fetch_m20_photos(sol=1)
    assert len(photos) == 1
    assert photos[0]["camera"]["name"] == "NAVCAM_LEFT"


@respx.mock
async def test_m20_connect_error_maps_to_unavailable(mars_client):
    respx.get(M20_BASE).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(NasaClientError) as exc:
        await mars_client.fetch_m20_photos(sol=1)
    assert exc.value.code == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_http_error_status_maps_to_unavailable(mars_client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(500))
    with pytest.raises(NasaClientError) as exc:
        await mars_client.fetch_msl_photos(sol=1)
    assert exc.value.code == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_invalid_json_maps_to_unavailable(mars_client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(200, content=b"not json"))
    with pytest.raises(NasaClientError) as exc:
        await mars_client.fetch_msl_photos(sol=1)
    assert exc.value.code == "MARS_ARCHIVE_UNAVAILABLE"


def test_normalize_msl_camera_unknown_passthrough():
    assert normalize_msl_camera("SOME_UNKNOWN_CODE") == "SOME_UNKNOWN_CODE"


def test_normalize_msl_camera_known():
    assert normalize_msl_camera("chemcam_rmi") == "CHEMCAM"


def test_sol_candidates_never_negative():
    from datetime import datetime, timezone

    landing = datetime.now(timezone.utc)
    candidates = sol_candidates(landing.date().isoformat(), landing)
    assert min(candidates) >= 0


def test_synthetic_id_is_stable_and_positive():
    a = synthetic_id("NLG_1911_0836586201_237ECM_N0892450NCAM00500_00_2I4J")
    b = synthetic_id("NLG_1911_0836586201_237ECM_N0892450NCAM00500_00_2I4J")
    assert a == b
    assert a > 0
    assert synthetic_id("different") != a
