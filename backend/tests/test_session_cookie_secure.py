from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_api_002_cookie_secure_follows_setting(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange

    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    start = await client.get("/api/v1/auth/oidc/start")
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/auth/oidc/callback",
        params={"code": "test-code", "state": state},
        follow_redirects=False,
    )
    set_cookie = callback.headers.get("set-cookie", "")
    assert "Secure" not in set_cookie

    get_settings.cache_clear()
