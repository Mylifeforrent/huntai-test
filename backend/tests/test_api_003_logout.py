import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_003_logout_revokes_session(
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

    logout = await client.post(
        "/api/v1/auth/session/logout",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert logout.status_code == 204

    me = await client.get("/api/v1/me")
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_003_logout_without_cookie_returns_204(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/session/logout")
    assert response.status_code == 204
