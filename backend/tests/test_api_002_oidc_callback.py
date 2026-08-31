from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_002_oidc_callback_sets_session_and_me_works(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange

    start = await client.get("/api/v1/auth/oidc/start", params={"return_path": "/home"})
    assert start.status_code == 200
    auth_url = start.json()["authorization_url"]
    query = parse_qs(urlparse(auth_url).query)
    state = query["state"][0]

    callback = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "/home"
    assert "huntai_session" in callback.headers.get("set-cookie", "")

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    data = me.json()["data"]
    assert data["user"]["display_name"] == "Test User"
    assert data["organization"]["slug"] == "test-org"
    assert len(data["memberships"]) == 1
