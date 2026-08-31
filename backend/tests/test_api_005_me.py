from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_005_me_returns_user_org_memberships(
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

    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "user" in data
    assert "organization" in data
    assert "memberships" in data
    assert "reauth_required" in data
    assert data["organization"]["capability_controls"]["ai_global_tightened"] is False


@pytest.mark.asyncio
async def test_api_005_me_unauthenticated_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"
