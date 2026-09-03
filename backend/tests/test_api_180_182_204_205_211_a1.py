"""Tests for API-180–182, 204–205, 211 A1 generation flow."""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.models import AIInvocationLog
from app.modules.identity_tenancy.models import Organization
from tests.ai_governance_helpers import seed_a1_model_routes
from tests.helpers import login_as

PARTIAL_OPENAPI = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/pets": {"get": {"summary": "list pets", "operationId": "listPets"}},
            "/broken": "not-an-object",
        },
    }
)

HAPPY_OPENAPI = json.dumps(
    {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/pets": {
                "get": {"summary": "list pets"},
                "post": {"summary": "create pet"},
            },
        },
    }
)

EMPTY_PATHS_OPENAPI = json.dumps({"openapi": "3.0.0", "paths": {}})


async def _wait_generation(client: AsyncClient, generation_id: str) -> dict[str, object]:
    for _ in range(20):
        response = await client.get(f"/api/v1/ai/generations/{generation_id}")
        status = response.json()["data"]["status"]
        if status in {"succeeded", "partial", "failed"}:
            return response.json()["data"]
        await asyncio.sleep(0.05)
    raise AssertionError("timeout waiting for generation")


@pytest.mark.asyncio
async def test_api_180_unauthenticated(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(uuid.uuid4()), "source_type": "openapi", "inline_content": "{}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_ac_024_partial_generation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_a1_model_routes(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client)
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": PARTIAL_OPENAPI,
        },
    )
    assert gen.status_code == 202
    generation_id = gen.json()["data"]["generation_id"]
    await _wait_generation(client, generation_id)
    drafts = await client.get(f"/api/v1/ai/generations/{generation_id}/drafts")
    assert drafts.status_code == 200
    body = drafts.json()["data"]
    assert body["status"] == "partial"
    assert len(body["failed_items"]) >= 1
    assert body["failed_items"][0]["endpoint"]
    assert body["failed_items"][0]["reason"]
    assert len(body["cases"]) >= 1


@pytest.mark.asyncio
async def test_ac_025_empty_paths_failed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_a1_model_routes(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client)
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": EMPTY_PATHS_OPENAPI,
        },
    )
    generation_id = gen.json()["data"]["generation_id"]
    status = await _wait_generation(client, generation_id)
    assert status["status"] == "failed"
    drafts = await client.get(f"/api/v1/ai/generations/{generation_id}/drafts")
    assert drafts.status_code == 422
    assert drafts.json()["error"]["code"] == "HT-ASYNC-002"


@pytest.mark.asyncio
async def test_happy_openapi_succeeded(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_a1_model_routes(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client)
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    generation_id = gen.json()["data"]["generation_id"]
    await _wait_generation(client, generation_id)
    drafts = await client.get(f"/api/v1/ai/generations/{generation_id}/drafts")
    body = drafts.json()["data"]
    assert body["status"] == "succeeded"
    assert body["failed_items"] == []
    assert len(body["cases"]) == 2


@pytest.mark.asyncio
async def test_api_205_does_not_create_test_cases(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    before = await client.get("/api/v1/test-cases", params={"project_id": str(project_id)})
    count = len(before.json()["data"]["items"])
    reg = await client.post(
        "/api/v1/import-sources",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    assert reg.status_code == 201
    assert "content" not in reg.text.lower() or "content_text" not in reg.text
    after = await client.get("/api/v1/test-cases", params={"project_id": str(project_id)})
    assert len(after.json()["data"]["items"]) == count


@pytest.mark.asyncio
async def test_kill_switch_blocks_180_not_205(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    org = await db_session.get(Organization, org_id)
    assert org is not None
    controls = dict(org.capability_controls)
    controls["tightened_capabilities"] = ["A1"]
    org.capability_controls = controls
    await db_session.commit()
    await login_as(client)
    blocked = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "HT-POL-001"
    allowed = await client.post(
        "/api/v1/import-sources",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    assert allowed.status_code == 201


@pytest.mark.asyncio
async def test_invoke_log_after_180(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    await seed_a1_model_routes(db_session, org_id=org_id, user_id=seeded_identity["user_id"])  # type: ignore[arg-type]
    await login_as(client)
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    generation_id = gen.json()["data"]["generation_id"]
    await _wait_generation(client, generation_id)
    result = await db_session.execute(
        select(AIInvocationLog).where(AIInvocationLog.organization_id == org_id)
    )
    assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_api_211_sse(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_a1_model_routes(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client)
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    generation_id = gen.json()["data"]["generation_id"]
    async with client.stream("GET", f"/api/v1/ai/generations/{generation_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = ""
        async for chunk in response.aiter_text():
            body += chunk
            if "event:" in body:
                break
        assert "event:" in body
        assert "command" not in body
        assert "save" not in body


@pytest.mark.asyncio
async def test_idempotency_replay_180(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_a1_model_routes(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client)
    key = str(uuid.uuid4())
    body = {
        "project_id": str(project_id),
        "source_type": "openapi",
        "inline_content": HAPPY_OPENAPI,
    }
    first = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": key},
        json=body,
    )
    second = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.json()["data"]["generation_id"] == second.json()["data"]["generation_id"]
    generation_id = first.json()["data"]["generation_id"]
    await _wait_generation(client, generation_id)
    third = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert third.json()["data"]["generation_id"] == generation_id
    after = await client.get(f"/api/v1/ai/generations/{generation_id}")
    assert after.json()["data"]["status"] in {"succeeded", "partial", "failed"}
    assert after.json()["data"]["status"] != "running"


@pytest.mark.asyncio
async def test_yaml_openapi_rejected_on_205_and_180(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    yaml_spec = "openapi: 3.0.0\npaths: {}\n"
    register = await client.post(
        "/api/v1/import-sources",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": yaml_spec,
        },
    )
    assert register.status_code == 400
    assert register.json()["error"]["code"] == "HT-VAL-003"
    generate = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": yaml_spec,
        },
    )
    assert generate.status_code == 400
    assert generate.json()["error"]["code"] == "HT-VAL-003"


@pytest.mark.asyncio
async def test_api_204_no_content(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    reg = await client.post(
        "/api/v1/import-sources",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "source_type": "openapi",
            "inline_content": HAPPY_OPENAPI,
        },
    )
    source_id = reg.json()["data"]["id"]
    detail = await client.get(f"/api/v1/import-sources/{source_id}")
    assert detail.status_code == 200
    assert "content_text" not in detail.json()["data"]
    assert detail.json()["data"]["checksum"]
