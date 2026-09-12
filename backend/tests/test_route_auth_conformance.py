"""S-M0-01: every API route must declare an auth dependency or be registered.

This is the fail-close net for tenant isolation at the API boundary: a newly
added route that forgets ``Depends(require_session)`` fails this test instead of
silently serving without a tenant context.

Scope limit (documented, not hidden): this proves no *route* is left ungated. It
does NOT prove every repository query filters ``organization_id`` — that remains
a per-function convention, see docs/11_test/test_report.md.
"""

from collections.abc import Iterator

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient

from app.main import create_app

# Dependencies that establish (or require) a tenant context.
AUTH_DEPENDENCIES = frozenset(
    {
        "require_session",
        "require_session_with_membership",
        "require_session_or_token_read",
        "require_api_token",
    }
)

# Routes that must stay reachable without a session, with the reason why.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/auth/oidc/start"): "API-001 OIDC login entry; no session exists yet",
    ("GET", "/api/v1/auth/oidc/callback"): "API-002 IdP redirect target; establishes the session",
    (
        "POST",
        "/api/v1/auth/session/logout",
    ): "API-003 idempotent logout; no-session call is a no-op 204",
    ("POST", "/api/v1/inbound-webhooks/{connector_id}"): (
        "API-090 inbound webhook; authenticated by HMAC signature, not a session"
    ),
    ("GET", "/healthz"): (
        "Stage 12 liveness probe; outside /api/v1, no API number, must be anonymous"
    ),
    ("GET", "/readyz"): (
        "Stage 12 readiness probe; outside /api/v1, no API number, must be anonymous"
    ),
}

# Routes that authenticate inside the handler instead of via a dependency.
# Each one is covered by a behavioural test below.
INLINE_AUTHENTICATED_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/test-runs"): (
        "API-062/080 accepts either a session or an execute-scope ApiToken, so it "
        "resolves the bearer-then-session precedence inline"
    ),
}


def _iter_api_routes(routes: object) -> Iterator[APIRoute]:
    """Walk the router tree, seeing through FastAPI's lazy _IncludedRouter wrappers."""
    for route in routes:  # type: ignore[union-attr]
        if isinstance(route, APIRoute):
            yield route
            continue
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _iter_api_routes(original.routes)


def _dependency_names(dependant: object) -> set[str]:
    names: set[str] = set()
    for sub in dependant.dependencies:  # type: ignore[union-attr]
        if sub.call is not None:
            names.add(getattr(sub.call, "__name__", str(sub.call)))
        names |= _dependency_names(sub)
    return names


def _route_keys() -> list[tuple[str, str, set[str]]]:
    keys: list[tuple[str, str, set[str]]] = []
    for route in _iter_api_routes(create_app().routes):
        names = _dependency_names(route.dependant)
        for method in sorted(route.methods):
            keys.append((method, route.path, names))
    return keys


def test_every_api_route_is_authenticated_or_registered() -> None:
    unclassified: list[str] = []
    for method, path, names in _route_keys():
        if names & AUTH_DEPENDENCIES:
            continue
        if (method, path) in PUBLIC_ROUTES or (method, path) in INLINE_AUTHENTICATED_ROUTES:
            continue
        unclassified.append(f"{method} {path}")

    assert unclassified == [], (
        f"route(s) have no auth dependency and are not registered as public/inline: {unclassified}"
    )


def test_route_registries_have_no_stale_entries() -> None:
    """A removed or renamed route must not leave a stale exemption behind."""
    present = {(method, path) for method, path, _ in _route_keys()}
    stale = sorted((set(PUBLIC_ROUTES) | set(INLINE_AUTHENTICATED_ROUTES)) - present)
    assert stale == [], f"registry entries no longer match any route: {stale}"


def test_registries_do_not_overlap() -> None:
    assert not set(PUBLIC_ROUTES) & set(INLINE_AUTHENTICATED_ROUTES)


@pytest.mark.asyncio
async def test_inline_authenticated_test_run_start_rejects_missing_credentials(
    client: AsyncClient,
) -> None:
    """API-062 must 401 (not 404) when neither a session nor a token is supplied."""
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": "00000000-0000-4000-8000-0000000000aa"},
        json={
            "project_id": "00000000-0000-4000-8000-0000000000bb",
            "env_id": "00000000-0000-4000-8000-0000000000cc",
            "execution_source": "script",
            "case_ids": ["00000000-0000-4000-8000-0000000000dd"],
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"
