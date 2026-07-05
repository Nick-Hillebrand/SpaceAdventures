"""Direct unit tests of apod_service — bypass FastAPI to verify coverage instrumentation."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.services import apod_service
from app.services.nasa_client import NasaClient, NasaClientError


def _client() -> NasaClient:
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        nasa_api_key="TEST",
        nasa_base_url="https://api.nasa.example",
    )
    return NasaClient(settings)


@pytest.fixture
async def nasa():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


@respx.mock
async def test_fetch_apod_cache_miss_writes_row(db_session, nasa):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(
            200,
            json={
                "date": "2020-03-15",
                "title": "T",
                "explanation": "E",
                "url": "u",
                "media_type": "image",
            },
        )
    )

    result = await apod_service.fetch_apod(db_session, nasa, "2020-03-15")
    assert result.cached is False
    assert result.stale is False
    assert result.row.title == "T"


@respx.mock
async def test_fetch_apod_stale_fallback_uses_cache(db_session, nasa):
    # Prime cache manually
    from datetime import datetime
    from app.models import Apod

    db_session.add(
        Apod(
            date="2020-04-01",
            title="Prev",
            explanation="e",
            url="u",
            media_type="image",
            fetched_at=datetime(2020, 4, 1),
        )
    )
    await db_session.commit()

    # Force today path: patch _is_today
    apod_service._is_today = lambda d: d == "2020-04-01"

    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(503)
    )

    result = await apod_service.fetch_apod(db_session, nasa, "2020-04-01")
    assert result.cached is True
    assert result.stale is True
    assert result.is_today is True


@respx.mock
async def test_fetch_apod_error_and_no_cache_raises(db_session, nasa):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(NasaClientError):
        await apod_service.fetch_apod(db_session, nasa, "2020-04-02")


async def test_fetch_apod_invalid_date_raises_valueerror(db_session, nasa):
    with pytest.raises(ValueError):
        await apod_service.fetch_apod(db_session, nasa, "not-a-date")
