"""Tests for API-030–035 test case lifecycle."""

import asyncio
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.ai_governance_helpers import seed_a1_model_routes, seed_tester
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_viewer


async def _poll_generation(
    client: AsyncClient,
    generation_id: str,
    *,
    max_attempts: int = 20,
) -> dict[str, object]:
    for _ in range(max_attempts):
        response = await client.get(f"/api/v1/ai/generations/{generation_id}")
        assert response.status_code == 200
        status = response.json()["data"]["status"]
        if status in {"succeeded", "partial", "failed"}:
            return response.json()["data"]
        await asyncio.sleep(0.05)
    raise AssertionError("generation did not complete")


@pytest.mark.asyncio
async def test_api_030_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/test-cases?project_id={uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_ac_022_generation_does_not_create_case_until_save(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_a1_model_routes(db_session, org_id=org_id, user_id=user_id)
    await login_as(client)

    list_before = await client.get("/api/v1/test-cases", params={"project_id": str(project_id)})
    assert list_before.status_code == 200
    count_before = len(list_before.json()["data"]["items"])

    openapi = json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "paths": {
                "/pets": {"get": {"summary": "list pets", "operationId": "listPets"}},
            },
        }
    )
    gen = await client.post(
        "/api/v1/ai/generations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "source_type": "openapi", "inline_content": openapi},
    )
    assert gen.status_code == 202
    generation_id = gen.json()["data"]["generation_id"]
    await _poll_generation(client, generation_id)

    list_mid = await client.get("/api/v1/test-cases", params={"project_id": str(project_id)})
    assert len(list_mid.json()["data"]["items"]) == count_before

    drafts = await client.get(f"/api/v1/ai/generations/{generation_id}/drafts")
    case = drafts.json()["data"]["cases"][0]
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": case["name"],
            "generation_id": generation_id,
            "drafts": [case],
        },
    )
    assert create.status_code == 201
    data = create.json()["data"]
    assert data["lifecycle_status"] == "DRAFT"
    assert "ai-generated" in data["tags"]

    list_after = await client.get(
        "/api/v1/test-cases",
        params={"project_id": str(project_id), "tags": "ai-generated"},
    )
    assert len(list_after.json()["data"]["items"]) == count_before + 1


@pytest.mark.asyncio
async def test_ac_023_extra_fields_rejected(
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
            "inline_content": '{"openapi":"3.0.0","paths":{"/x":{"get":{}}}}',
            "save": True,
        },
    )
    assert gen.status_code == 400
    assert gen.json()["error"]["code"] == "HT-VAL-001"

    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": "t",
            "lifecycle_status": "ACTIVE",
        },
    )
    assert create.status_code == 400
    assert create.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_ac_026_review_lifecycle(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": "Review me",
            "tags": ["ai-generated"],
        },
    )
    assert create.status_code == 201
    case_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    review_early = await client.post(
        f"/api/v1/test-cases/{case_id}/review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "decision": "approve"},
    )
    assert review_early.status_code == 409
    assert review_early.json()["error"]["code"] == "HT-STATE-001"

    submit = await client.post(
        f"/api/v1/test-cases/{case_id}/submit-review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    assert submit.status_code == 200
    pending_version = submit.json()["data"]["version"]

    approve = await client.post(
        f"/api/v1/test-cases/{case_id}/review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": pending_version, "decision": "approve"},
    )
    assert approve.status_code == 200
    assert approve.json()["data"]["lifecycle_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_viewer_cannot_create(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_viewer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
        idp_subject="viewer-cases",
    )
    await login_as(client, idp_subject="viewer-cases")
    response = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": "x",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_tester_cannot_review(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await seed_tester(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
        idp_subject="tester-cases",
    )
    await login_as(client, idp_subject="tester-cases")
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": "pending",
        },
    )
    case_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]
    await client.post(
        f"/api/v1/test-cases/{case_id}/submit-review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    await login_as(client, idp_subject="tester-cases")
    review = await client.post(
        f"/api/v1/test-cases/{case_id}/review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version + 1, "decision": "approve"},
    )
    assert review.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.get(f"/api/v1/test-cases/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_source_parser_invalid_json() -> None:
    from app.modules.test_assets.source_parser import parse_openapi_content

    with pytest.raises(ValueError, match="file_validation"):
        parse_openapi_content("not-json")
