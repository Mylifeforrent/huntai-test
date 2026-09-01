from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_001_oidc_start_returns_authorization_url(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/oidc/start", params={"return_path": "/dashboard"})
    assert response.status_code == 200
    body = response.json()
    assert "authorization_url" in body
    parsed = urlparse(body["authorization_url"])
    assert parsed.hostname == "idp.example.com"
    query = parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert "state" in query
    assert "code_challenge" in query


@pytest.mark.asyncio
async def test_api_001_oidc_start_rejects_open_redirect(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/oidc/start", params={"return_path": "//evil.com"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "HT-VAL-005"


@pytest.mark.asyncio
async def test_api_001_oidc_start_rejects_callback_return_path(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/oidc/start",
        params={"return_path": "/api/v1/auth/oidc/callback?code=x&state=y"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-005"
