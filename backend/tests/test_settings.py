from __future__ import annotations


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


async def test_nasa_key_mutation_endpoint_removed(client):
    """The unauthenticated key-mutation endpoint must not exist."""
    response = await client.post(
        "/api/v1/settings/nasa-api-key", json={"api_key": "attacker-key"}
    )
    assert response.status_code in (404, 405)
    # Server state unchanged
    body = (await client.get("/api/v1/settings")).json()
    assert body["nasa_key_set"] is True


async def test_n2yo_key_mutation_endpoint_removed(client):
    """The unauthenticated key-mutation endpoint must not exist."""
    response = await client.post(
        "/api/v1/settings/n2yo-api-key", json={"api_key": ""}
    )
    assert response.status_code in (404, 405)
    body = (await client.get("/api/v1/settings")).json()
    assert body["n2yo_key_set"] is True
