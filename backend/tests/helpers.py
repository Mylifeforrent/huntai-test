"""Shared async HTTP test helpers."""

from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient


async def login_as(
    client: AsyncClient,
    *,
    idp_subject: str = "test-subject-001",
) -> None:
    """Complete OIDC start→callback with a test double for the given IdP subject."""

    async def verify_side_effect(
        settings: Any, *, id_token: str, expected_nonce: str
    ) -> dict[str, Any]:
        _ = settings
        _ = id_token
        return {"sub": idp_subject, "nonce": expected_nonce}

    with (
        patch(
            "app.modules.identity_tenancy.service.exchange_oidc_code",
            new_callable=AsyncMock,
        ) as mock_exchange,
        patch(
            "app.modules.identity_tenancy.service.verify_id_token",
            new_callable=AsyncMock,
        ) as mock_verify,
    ):
        mock_exchange.return_value = {
            "id_token": "verified-by-test-double",
            "access_token": "redacted",
        }
        mock_verify.side_effect = verify_side_effect
        start = await client.get("/api/v1/auth/oidc/start")
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        await client.get(
            "/api/v1/auth/oidc/callback",
            params={"code": "test-code", "state": state},
            follow_redirects=False,
        )
