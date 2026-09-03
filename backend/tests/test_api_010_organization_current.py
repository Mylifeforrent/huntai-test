from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_010_organization_current_returns_org(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange

    start = await client.get("/api/v1/auth/oidc/start")
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )

    response = await client.get("/api/v1/organizations/current")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["slug"] == "test-org"
    assert data["name"] == "Test Org"
    assert "capability_controls" in data
    assert "created_at" in data
    assert "updated_at" in data
