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


@pytest.mark.asyncio
async def test_api_002_missing_code_redirects_to_spa_recovery(client: AsyncClient) -> None:
    start = await client.get("/api/v1/auth/oidc/start", params={"return_path": "/home"})
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "/home?oidc=failed"
    assert "set-cookie" not in {key.lower() for key in callback.headers}


@pytest.mark.asyncio
async def test_api_002_idp_error_redirects_to_spa_recovery(client: AsyncClient) -> None:
    start = await client.get("/api/v1/auth/oidc/start", params={"return_path": "/projects"})
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"error": "login_required", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    location = callback.headers["location"]
    assert location == "/projects?oidc=failed"
    assert "code=" not in location
    assert "state=" not in location
    assert "error_description" not in location


@pytest.mark.asyncio
async def test_api_002_invalid_state_redirects_home_recovery(client: AsyncClient) -> None:
    callback = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "x", "state": "unknown-state"},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == "/?oidc=failed"
