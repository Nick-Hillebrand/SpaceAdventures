from __future__ import annotations

import pytest


async def test_get_settings_returns_key_status(client):
    """GET /api/v1/settings returns boolean key-set flags."""
    response = await client.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["nasa_key_set"] is True   # fixture sets nasa_api_key="TEST_KEY"
    assert body["n2yo_key_set"] is True   # fixture sets n2yo_api_key="TEST_N2YO"


async def test_get_settings_does_not_leak_key_values(client):
    """GET /api/v1/settings never exposes the actual key strings."""
    response = await client.get("/api/v1/settings")
    body = response.json()
    assert "nasa_api_key" not in body
    assert "n2yo_api_key" not in body
    # Only the boolean flags are present
    assert set(body.keys()) == {"nasa_key_set", "n2yo_key_set"}


async def test_set_nasa_api_key_success(client):
    """POST /nasa-api-key updates the in-process key and GET reflects the change."""
    # Clear the key first so we can test the transition to True
    await client.post("/api/v1/settings/nasa-api-key", json={"api_key": ""})
    assert (await client.get("/api/v1/settings")).json()["nasa_key_set"] is False

    response = await client.post("/api/v1/settings/nasa-api-key", json={"api_key": "brand-new-key"})
    assert response.status_code == 200

    get = await client.get("/api/v1/settings")
    assert get.json()["nasa_key_set"] is True


async def test_set_n2yo_api_key_success(client):
    """POST /n2yo-api-key updates the in-process key and GET reflects the change."""
    await client.post("/api/v1/settings/n2yo-api-key", json={"api_key": ""})
    assert (await client.get("/api/v1/settings")).json()["n2yo_key_set"] is False

    response = await client.post("/api/v1/settings/n2yo-api-key", json={"api_key": "brand-new-n2yo-key"})
    assert response.status_code == 200

    get = await client.get("/api/v1/settings")
    assert get.json()["n2yo_key_set"] is True


async def test_clear_nasa_key(client):
    """POSTing an empty string marks nasa_key_set as False."""
    response = await client.post("/api/v1/settings/nasa-api-key", json={"api_key": ""})
    assert response.status_code == 200
    body = (await client.get("/api/v1/settings")).json()
    assert body["nasa_key_set"] is False


async def test_clear_n2yo_key(client):
    """POSTing an empty string marks n2yo_key_set as False."""
    response = await client.post("/api/v1/settings/n2yo-api-key", json={"api_key": ""})
    assert response.status_code == 200
    body = (await client.get("/api/v1/settings")).json()
    assert body["n2yo_key_set"] is False


async def test_set_nasa_key_invalid_body(client):
    """POST /nasa-api-key with missing api_key field returns 422."""
    response = await client.post("/api/v1/settings/nasa-api-key", json={"wrong_field": "value"})
    assert response.status_code == 422


async def test_set_n2yo_key_invalid_body(client):
    """POST /n2yo-api-key with missing api_key field returns 422."""
    response = await client.post("/api/v1/settings/n2yo-api-key", json={})
    assert response.status_code == 422
