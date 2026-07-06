from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.services.nasa_client import NasaClient, NasaClientError


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        nasa_api_key="TEST_KEY",
        nasa_base_url="https://api.nasa.example",
    )


@pytest.fixture
async def nasa_client():
    client = NasaClient(_settings())
    try:
        yield client
    finally:
        await client.close()


@respx.mock
async def test_get_success(nasa_client):
    route = respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(200, json={"title": "APOD"}),
    )
    data = await nasa_client.get("/planetary/apod", params={"date": "2026-07-04"})
    assert data == {"title": "APOD"}
    assert route.called
    # Confirms api_key is injected
    assert "api_key=TEST_KEY" in str(route.calls.last.request.url)


@respx.mock
async def test_get_success_ignores_none_params(nasa_client):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(200, json={"ok": True}),
    )
    assert await nasa_client.get("/planetary/apod", params={"date": None}) == {"ok": True}


@respx.mock
async def test_get_auth_error(nasa_client):
    respx.get("https://api.nasa.example/x").mock(return_value=httpx.Response(403))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_AUTH_ERROR"


@respx.mock
async def test_get_auth_error_401(nasa_client):
    respx.get("https://api.nasa.example/x").mock(return_value=httpx.Response(401))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_AUTH_ERROR"


@respx.mock
async def test_get_upstream_unavailable_on_5xx(nasa_client):
    respx.get("https://api.nasa.example/x").mock(return_value=httpx.Response(503))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_UNAVAILABLE"


@respx.mock
async def test_get_nasa_error_on_4xx(nasa_client):
    respx.get("https://api.nasa.example/x").mock(return_value=httpx.Response(404))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_ERROR"


@respx.mock
async def test_get_404_treated_as_unavailable_when_opted_in(nasa_client):
    respx.get("https://api.nasa.example/x").mock(return_value=httpx.Response(404))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x", treat_404_as_unavailable=True)
    assert exc.value.code == "NASA_UNAVAILABLE"


@respx.mock
async def test_get_invalid_json_returns_nasa_error(nasa_client):
    respx.get("https://api.nasa.example/x").mock(
        return_value=httpx.Response(200, content=b"not json"),
    )
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_ERROR"


@respx.mock
async def test_get_timeout_maps_to_unavailable(nasa_client):
    respx.get("https://api.nasa.example/x").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_UNAVAILABLE"


@respx.mock
async def test_connect_error_probes_and_returns_no_internet(nasa_client):
    respx.get("https://api.nasa.example/x").mock(side_effect=httpx.ConnectError("boom"))
    respx.head("https://www.google.com").mock(side_effect=httpx.ConnectError("no net"))

    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NO_INTERNET"


@respx.mock
async def test_connect_error_probes_and_returns_nasa_unavailable(nasa_client):
    respx.get("https://api.nasa.example/x").mock(side_effect=httpx.ConnectError("boom"))
    respx.head("https://www.google.com").mock(return_value=httpx.Response(200))

    with pytest.raises(NasaClientError) as exc:
        await nasa_client.get("/x")
    assert exc.value.code == "NASA_UNAVAILABLE"


async def test_error_carries_message_and_status():
    err = NasaClientError("NASA_ERROR", "boom")
    assert err.code == "NASA_ERROR"
    assert err.message == "boom"
    assert err.status_code == 502
    assert str(err) == "boom"
