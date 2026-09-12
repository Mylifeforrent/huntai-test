"""Stage 12 ops probes: liveness and readiness.

These endpoints are unauthenticated by design, so the tests pin two properties:
they answer without a session, and a failing readiness check never leaks
infrastructure detail.
"""

import pytest
from httpx import AsyncClient

from app.api import ops


@pytest.mark.asyncio
async def test_healthz_is_anonymous_and_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_reports_ready_when_database_reachable(
    client: AsyncClient, seeded_identity: dict[str, object]
) -> None:
    _ = seeded_identity
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_readyz_reports_not_ready_without_leaking_internals(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_dsn = "postgresql+asyncpg://user:sup3r-s3cret@db.internal:5432/huntai"

    def broken_engine() -> None:
        raise RuntimeError(f"could not connect to {secret_dsn}")

    monkeypatch.setattr(ops, "get_engine", broken_engine)

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    # The unauthenticated probe must not become an infrastructure oracle.
    assert "sup3r-s3cret" not in response.text
    assert "postgresql" not in response.text
    assert "db.internal" not in response.text
    assert "RuntimeError" not in response.text
