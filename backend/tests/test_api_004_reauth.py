from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_004_reauth_returns_authorization_url(
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

    response = await client.post("/api/v1/auth/reauth")
    assert response.status_code == 200
    body = response.json()
    assert body["reauth_satisfied"] is False
    assert "authorization_url" in body
