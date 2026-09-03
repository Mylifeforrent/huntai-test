"""Tests for API-140–143 quality gate policy CRUD."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    User,
)
from app.modules.quality_gates.models import QualityGatePolicy
from tests.ai_governance_helpers import seed_tester
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_viewer

THRESHOLDS = {
    "min_pass_rate": 95,
    "max_p95_ms": 500,
    "max_error_rate": 1,
}


def _create_body(
    project_id: uuid.UUID,
    *,
    mode: str = "report_only",
    confirm_blocking: bool | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "project_id": str(project_id),
        "thresholds": thresholds or dict(THRESHOLDS),
        "mode": mode,
        "scope": {},
    }
    if confirm_blocking is not None:
        body["confirm_blocking"] = confirm_blocking
    return body


@pytest.mark.asyncio
async def test_api_140_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/quality-gate-policies?project_id={uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_140_missing_project_id(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    _ = seeded_identity
    await login_as(client)
    response = await client.get("/api/v1/quality-gate-policies")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_happy_path_crud_and_idempotency(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    idem_key = str(uuid.uuid4())
    create = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": idem_key},
        json=_create_body(project_id),
    )
    assert create.status_code == 201
    policy_id = create.json()["data"]["id"]
    assert create.json()["data"]["mode"] == "report_only"
    assert create.json()["data"]["policy_version"] == 1

    list_resp = await client.get(
        "/api/v1/quality-gate-policies",
        params={"project_id": str(project_id)},
    )
    assert list_resp.status_code == 200
    assert any(item["id"] == policy_id for item in list_resp.json()["data"]["items"])

    detail = await client.get(f"/api/v1/quality-gate-policies/{policy_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["scope"] == {}

    version = detail.json()["data"]["version"]
    policy_version = detail.json()["data"]["policy_version"]
    patch = await client.patch(
        f"/api/v1/quality-gate-policies/{policy_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "thresholds": {
                "min_pass_rate": 90,
                "max_p95_ms": 600,
                "max_error_rate": 2,
            },
        },
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["id"] == policy_id
    assert patch.json()["data"]["policy_version"] == policy_version + 1
    assert patch.json()["data"]["thresholds"]["min_pass_rate"] == 90

    replay = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": idem_key},
        json=_create_body(project_id),
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == policy_id


@pytest.mark.asyncio
async def test_create_blocking_requires_confirm(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    denied = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id, mode="blocking"),
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "HT-VAL-001"

    allowed = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id, mode="blocking", confirm_blocking=True),
    )
    assert allowed.status_code == 201
    assert allowed.json()["data"]["mode"] == "blocking"


@pytest.mark.asyncio
async def test_patch_blocking_requires_confirm(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    create = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id),
    )
    policy_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    denied = await client.patch(
        f"/api/v1/quality-gate-policies/{policy_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "mode": "blocking"},
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "HT-VAL-001"

    allowed = await client.patch(
        f"/api/v1/quality-gate-policies/{policy_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "mode": "blocking",
            "confirm_blocking": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["mode"] == "blocking"


@pytest.mark.asyncio
async def test_tester_viewer_read_only(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)

    await login_as(client)
    create = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id),
    )
    policy_id = create.json()["data"]["id"]

    await seed_tester(
        db_session,
        org_id=org_id,
        project_id=project_id,
        idp_subject="tester-gate",
    )
    await login_as(client, idp_subject="tester-gate")

    list_resp = await client.get(
        "/api/v1/quality-gate-policies",
        params={"project_id": str(project_id)},
    )
    assert list_resp.status_code == 200
    detail = await client.get(f"/api/v1/quality-gate-policies/{policy_id}")
    assert detail.status_code == 200

    forbidden = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(
            project_id,
            thresholds={"min_pass_rate": 80, "max_p95_ms": 800, "max_error_rate": 3},
        ),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "HT-IAM-001"

    await _seed_viewer(
        db_session,
        org_id=org_id,
        project_id=project_id,
        idp_subject="viewer-gate",
    )
    await login_as(client, idp_subject="viewer-gate")
    viewer_list = await client.get(
        "/api/v1/quality-gate-policies",
        params={"project_id": str(project_id)},
    )
    assert viewer_list.status_code == 200
    viewer_post = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id),
    )
    assert viewer_post.status_code == 403
    assert viewer_post.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_patch_cas_stale(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    create = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id),
    )
    policy_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    conflict = await client.patch(
        f"/api/v1/quality-gate-policies/{policy_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version + 99, "mode": "report_only"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_get_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    _ = seeded_identity
    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    other_project = uuid.uuid4()
    policy_id = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Foreign Org",
            slug="foreign-org-gate",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=other_user,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            idp_subject="foreign-gate",
            display_name="Foreign",
            email="foreign@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=other_project,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            name="Foreign Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    db_session.add(
        QualityGatePolicy(
            id=policy_id,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            thresholds=dict(THRESHOLDS),
            mode="report_only",
            scope={},
            policy_version=1,
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get(f"/api/v1/quality-gate-policies/{policy_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_idempotency_conflict(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    key = str(uuid.uuid4())
    first = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": key},
        json=_create_body(project_id),
    )
    assert first.status_code == 201

    conflict = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": key},
        json=_create_body(
            project_id,
            thresholds={"min_pass_rate": 80, "max_p95_ms": 800, "max_error_rate": 3},
        ),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-IDEM-001"


@pytest.mark.asyncio
async def test_list_mode_filter(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id),
    )
    await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(project_id, mode="blocking", confirm_blocking=True),
    )

    filtered = await client.get(
        "/api/v1/quality-gate-policies",
        params={"project_id": str(project_id), "mode": "report_only"},
    )
    assert filtered.status_code == 200
    items = filtered.json()["data"]["items"]
    assert items
    assert all(item["mode"] == "report_only" for item in items)
