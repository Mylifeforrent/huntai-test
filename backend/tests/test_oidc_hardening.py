"""S-M0-01 hardening: OIDC discovery endpoints, token validation, prod guard.

These tests never touch the network: discovery and JWKS HTTP are served through
``httpx.MockTransport``, and ID tokens are signed in-test with a generated RSA
key. The real IdP remains unverifiable locally (see docs/11_test/test_report.md).
"""

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.core.config import Settings, loopback_issuer_host
from app.modules.identity_tenancy import service

ISSUER = "https://idp.example.com"
CLIENT_ID = "test-client"
KID = "hardening-test-kid"
FAR_FUTURE_EXP = 4102444800  # 2100-01-01


def _b64url(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _install_http(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Route every service-module httpx call through a MockTransport."""
    # Captured before patching: service.httpx is the httpx module itself.
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(service.httpx, "AsyncClient", factory)


@pytest.fixture
def signing_key() -> tuple[str, dict[str, Any]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()
    ).decode()
    public_jwk = JsonWebKey.import_key(
        key.public_key().public_bytes(ser.Encoding.PEM, ser.PublicFormat.SubjectPublicKeyInfo)
    ).as_dict()
    public_jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return private_pem, {"keys": [public_jwk]}


def _sign(private_pem: str, claims: dict[str, Any], *, alg: str = "RS256") -> str:
    token = JsonWebToken([alg]).encode({"alg": alg, "kid": KID}, claims, private_pem)
    return token.decode() if isinstance(token, bytes) else token


def _claims(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sub": "test-subject-001",
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "nonce": "expected-nonce",
        "exp": FAR_FUTURE_EXP,
    }
    base.update(overrides)
    return base


def _seed_metadata(monkeypatch: pytest.MonkeyPatch, jwks_uri: str = f"{ISSUER}/jwks-test") -> None:
    service.clear_oidc_metadata_cache()
    monkeypatch.setitem(
        service._oidc_metadata_cache,
        ISSUER,
        {
            "issuer": ISSUER,
            "authorization_endpoint": f"{ISSUER}/oauth2/v2/authorize",
            "token_endpoint": f"{ISSUER}/oauth2/v2/token",
            "jwks_uri": jwks_uri,
        },
    )


# --- discovery -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_serves_endpoints_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.clear_oidc_metadata_cache()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/oauth2/v2/authorize",
                "token_endpoint": f"{ISSUER}/oauth2/v2/token",
                "jwks_uri": f"{ISSUER}/oauth2/v2/jwks",
            },
        )

    _install_http(monkeypatch, handler)
    metadata = await service.fetch_oidc_metadata(service.get_settings())

    assert metadata["authorization_endpoint"] == f"{ISSUER}/oauth2/v2/authorize"
    assert calls == [f"{ISSUER}/.well-known/openid-configuration"]

    # Second call must be served from cache, not the network.
    await service.fetch_oidc_metadata(service.get_settings())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_rejects_issuer_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.clear_oidc_metadata_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(
            200,
            json={
                "issuer": "https://evil.example.com",
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks",
            },
        )

    _install_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="issuer_mismatch"):
        await service.fetch_oidc_metadata(service.get_settings())


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_requires_jwks_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.clear_oidc_metadata_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(
            200,
            json={
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
            },
        )

    _install_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="missing_jwks_uri"):
        await service.fetch_oidc_metadata(service.get_settings())


@pytest.mark.asyncio
async def test_fetch_oidc_metadata_rejects_non_object_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service.clear_oidc_metadata_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(200, json=["not", "an", "object"])

    _install_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="invalid_oidc_metadata"):
        await service.fetch_oidc_metadata(service.get_settings())


# --- id token validation -------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_id_token_accepts_valid_token(
    monkeypatch: pytest.MonkeyPatch, signing_key: tuple[str, dict[str, Any]]
) -> None:
    private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))

    claims = await service.verify_id_token(
        service.get_settings(),
        id_token=_sign(private_pem, _claims()),
        expected_nonce="expected-nonce",
    )
    assert claims["sub"] == "test-subject-001"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"iss": "https://evil.example.com"}, id="wrong-issuer"),
        pytest.param({"aud": "other-client"}, id="wrong-audience"),
        pytest.param({"exp": 1}, id="expired"),
    ],
)
async def test_verify_id_token_rejects_bad_claims(
    monkeypatch: pytest.MonkeyPatch,
    signing_key: tuple[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> None:
    private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))

    with pytest.raises(ValueError, match="id_token_invalid"):
        await service.verify_id_token(
            service.get_settings(),
            id_token=_sign(private_pem, _claims(**overrides)),
            expected_nonce="expected-nonce",
        )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_hmac_algorithm(
    monkeypatch: pytest.MonkeyPatch, signing_key: tuple[str, dict[str, Any]]
) -> None:
    """A shared-secret MAC would let the client forge tokens."""
    _private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))

    forged = JsonWebToken(["HS256"]).encode(
        {"alg": "HS256", "kid": KID}, _claims(), b"attacker-controlled-secret"
    )
    forged_str = forged.decode() if isinstance(forged, bytes) else forged
    with pytest.raises(ValueError, match="id_token_invalid"):
        await service.verify_id_token(
            service.get_settings(), id_token=forged_str, expected_nonce="expected-nonce"
        )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_unsigned_token(
    monkeypatch: pytest.MonkeyPatch, signing_key: tuple[str, dict[str, Any]]
) -> None:
    _private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))

    unsigned = f"{_b64url({'alg': 'none'})}.{_b64url(_claims())}."
    with pytest.raises(ValueError, match="id_token_invalid"):
        await service.verify_id_token(
            service.get_settings(), id_token=unsigned, expected_nonce="expected-nonce"
        )


@pytest.mark.asyncio
async def test_verify_id_token_rejects_nonce_mismatch(
    monkeypatch: pytest.MonkeyPatch, signing_key: tuple[str, dict[str, Any]]
) -> None:
    private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))

    with pytest.raises(ValueError, match="nonce_mismatch"):
        await service.verify_id_token(
            service.get_settings(),
            id_token=_sign(private_pem, _claims(nonce="replayed-nonce")),
            expected_nonce="expected-nonce",
        )


@pytest.mark.asyncio
async def test_verify_id_token_enforces_azp_for_multi_audience(
    monkeypatch: pytest.MonkeyPatch, signing_key: tuple[str, dict[str, Any]]
) -> None:
    private_pem, jwks = signing_key
    _seed_metadata(monkeypatch)
    _install_http(monkeypatch, lambda request: httpx.Response(200, json=jwks))
    multi_aud = {"aud": [CLIENT_ID, "another-client"]}

    with pytest.raises(ValueError, match="azp_mismatch"):
        await service.verify_id_token(
            service.get_settings(),
            id_token=_sign(private_pem, _claims(azp="another-client", **multi_aud)),
            expected_nonce="expected-nonce",
        )

    claims = await service.verify_id_token(
        service.get_settings(),
        id_token=_sign(private_pem, _claims(azp=CLIENT_ID, **multi_aud)),
        expected_nonce="expected-nonce",
    )
    assert claims["azp"] == CLIENT_ID


# --- production guard ----------------------------------------------------------


@pytest.mark.parametrize(
    ("issuer", "expected_host"),
    [
        ("http://127.0.0.1:8090", "127.0.0.1"),
        ("http://localhost:8090", "localhost"),
        ("http://[::1]:8090", "::1"),
        ("http://0.0.0.0:8090", "0.0.0.0"),
        ("http://127.0.0.2:8090", "127.0.0.2"),
    ],
)
def test_loopback_issuer_host_detects_local_issuers(issuer: str, expected_host: str) -> None:
    assert loopback_issuer_host(issuer) == expected_host


@pytest.mark.parametrize(
    "issuer",
    ["https://idp.example.com", "https://sso.corp.internal", "https://10.1.2.3", "not a url"],
)
def test_loopback_issuer_host_accepts_non_local_issuers(issuer: str) -> None:
    assert loopback_issuer_host(issuer) is None


def _settings_kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "app_env": "development",
        "app_port": 8000,
        "log_level": "warning",
        "database_url": "postgresql+asyncpg://postgres@127.0.0.1:5432/huntai_test",
        "session_cookie_name": "huntai_session",
        "session_cookie_samesite": "Lax",
        "session_cookie_secure": True,
        "session_ttl_seconds": 3600,
        "oidc_login_draft_ttl_seconds": 600,
        "reauth_window_seconds": 900,
        "approval_ttl_seconds": 86400,
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": "test-secret",
        "oidc_redirect_uri": "http://localhost:8000/api/v1/auth/oidc/callback",
        "oidc_claim_subject": "sub",
        "github_webhook_secret": "test-github-webhook-secret",
        "artifact_root": "/tmp/huntai-test-artifacts",
    }
    base.update(overrides)
    return base


def test_settings_rejects_loopback_issuer_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **_settings_kwargs(app_env="production", oidc_issuer="http://127.0.0.1:8090"),
        )


def test_settings_allows_public_issuer_in_production() -> None:
    settings = Settings(_env_file=None, **_settings_kwargs(app_env="production"))
    assert settings.oidc_issuer == ISSUER


def test_settings_allows_loopback_issuer_outside_production() -> None:
    settings = Settings(_env_file=None, **_settings_kwargs(oidc_issuer="http://127.0.0.1:8090"))
    assert settings.app_env == "development"
