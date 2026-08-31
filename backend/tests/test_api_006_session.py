from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_006_session_returns_metadata(
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

    response = await client.get("/api/v1/auth/session")
    assert response.status_code == 200
    body = response.json()
    assert "expires_at" in body
    assert "reauth_required" in body
    assert isinstance(body["reauth_required"], bool)


@pytest.mark.asyncio
async def test_api_006_session_unauthenticated_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/session")
    assert response.status_code == 401
