"""Tests for API-050–055 test plan CRUD."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    User,
)
from app.modules.run_orchestration.models import TestRun
from app.modules.test_assets.models import TestCase, TestPlan
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_viewer


async def _insert_test_case(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str = "Plan case",
) -> uuid.UUID:
    now = datetime.now(UTC)
    case_id = uuid.uuid4()
    db_session.add(
        TestCase(
            id=case_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            case_type="api",
            execution_mode="script",
            title=title,
            priority="P2",
            tags=[],
            lifecycle_status="DRAFT",
            validity="valid",
            invalid_reason=None,
            invalidated_at=None,
            script_ref=None,
            job_binding=None,
            jira_story_key=None,
            current_version_id=None,
        )
    )
    await db_session.commit()
    return case_id


async def _count_runs_for_plan(db_session: AsyncSession, *, plan_id: uuid.UUID) -> int:
    result = await db_session.execute(
        select(func.count(TestRun.id)).where(TestRun.plan_id == plan_id)
    )
    return int(result.scalar_one())


@pytest.mark.asyncio
async def test_api_050_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/test-plans?project_id={uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_050_missing_project_id(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    _ = seeded_identity
    await login_as(client)
    response = await client.get("/api/v1/test-plans")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_ac_094_independent_steps(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await login_as(client)

    idem_key = str(uuid.uuid4())
    create = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": idem_key},
        json={"project_id": str(project_id), "name": "Regression A", "jira_fix_version": "1.0"},
    )
    assert create.status_code == 201
    plan_id = create.json()["data"]["id"]
    assert create.json()["data"]["case_ids"] == []

    detail = await client.get(f"/api/v1/test-plans/{plan_id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["case_ids"] == []
    assert body["schedule"] is None
    assert body["report_aggregate"]["last_run_id"] is None
    assert await _count_runs_for_plan(db_session, plan_id=uuid.UUID(plan_id)) == 0

    case_id = await _insert_test_case(
        db_session,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
    )
    bind = await client.put(
        f"/api/v1/test-plans/{plan_id}/case-ids",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": body["version"], "case_ids": [str(case_id)]},
    )
    assert bind.status_code == 200
    assert bind.json()["data"]["case_ids"] == [str(case_id)]

    after_bind = await client.get(f"/api/v1/test-plans/{plan_id}")
    assert after_bind.json()["data"]["case_ids"] == [str(case_id)]
    assert after_bind.json()["data"]["schedule"] is None
    assert await _count_runs_for_plan(db_session, plan_id=uuid.UUID(plan_id)) == 0

    version = after_bind.json()["data"]["version"]
    schedule_put = await client.put(
        f"/api/v1/test-plans/{plan_id}/schedule",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "enabled": True,
            "schedule": {"expr": "opaque"},
        },
    )
    assert schedule_put.status_code == 200

    after_schedule = await client.get(f"/api/v1/test-plans/{plan_id}")
    schedule = after_schedule.json()["data"]["schedule"]
    assert schedule is not None
    assert schedule["enabled"] is True
    assert schedule["schedule"] == {"expr": "opaque"}
    assert await _count_runs_for_plan(db_session, plan_id=uuid.UUID(plan_id)) == 0

    replay = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": idem_key},
        json={"project_id": str(project_id), "name": "Regression A", "jira_fix_version": "1.0"},
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == plan_id

    listed = await client.get("/api/v1/test-plans", params={"project_id": str(project_id)})
    assert listed.status_code == 200
    assert len(listed.json()["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_viewer_read_only(
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
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "Viewer plan"},
    )
    assert create.status_code == 201
    plan_id = create.json()["data"]["id"]

    await _seed_viewer(db_session, org_id=org_id, project_id=project_id, idp_subject="viewer-plan")
    await login_as(client, idp_subject="viewer-plan")

    list_resp = await client.get("/api/v1/test-plans", params={"project_id": str(project_id)})
    assert list_resp.status_code == 200
    detail = await client.get(f"/api/v1/test-plans/{plan_id}")
    assert detail.status_code == 200

    forbidden = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "Denied"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_patch_cas_conflict(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)

    create = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "CAS plan"},
    )
    plan_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    conflict = await client.patch(
        f"/api/v1/test-plans/{plan_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version + 99, "name": "Stale"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_put_case_ids_cross_project(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    other_project = uuid.uuid4()
    now = datetime.now(UTC)
    db_session.add(
        Project(
            id=other_project,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            name="Other",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.commit()

    foreign_case = await _insert_test_case(
        db_session,
        org_id=org_id,
        project_id=other_project,
        user_id=user_id,
    )

    await login_as(client)
    create = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "Cross project"},
    )
    plan_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    bad = await client.put(
        f"/api/v1/test-plans/{plan_id}/case-ids",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "case_ids": [str(foreign_case)]},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "HT-VAL-001"


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
    plan_id = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Foreign Org",
            slug="foreign-org-plan",
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
            idp_subject="foreign-plan",
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
        TestPlan(
            id=plan_id,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            name="Secret plan",
            jira_fix_version=None,
            schedule_binding=None,
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get(f"/api/v1/test-plans/{plan_id}")
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
        "/api/v1/test-plans",
        headers={"Idempotency-Key": key},
        json={"project_id": str(project_id), "name": "Idem A"},
    )
    assert first.status_code == 201

    conflict = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": key},
        json={"project_id": str(project_id), "name": "Idem B"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-IDEM-001"


@pytest.mark.asyncio
async def test_put_case_ids_empty_unbinds(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    case_id = await _insert_test_case(
        db_session,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
    )
    await login_as(client)

    create = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "Unbind"},
    )
    plan_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    bind = await client.put(
        f"/api/v1/test-plans/{plan_id}/case-ids",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "case_ids": [str(case_id)]},
    )
    version = bind.json()["data"]["version"]

    unbind = await client.put(
        f"/api/v1/test-plans/{plan_id}/case-ids",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "case_ids": []},
    )
    assert unbind.status_code == 200
    assert unbind.json()["data"]["case_ids"] == []

    detail = await client.get(f"/api/v1/test-plans/{plan_id}")
    assert detail.json()["data"]["case_ids"] == []


@pytest.mark.asyncio
async def test_patch_does_not_change_case_ids(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    case_id = await _insert_test_case(
        db_session,
        org_id=org_id,
        project_id=project_id,
        user_id=user_id,
    )
    await login_as(client)

    create = await client.post(
        "/api/v1/test-plans",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "name": "Patch cases"},
    )
    plan_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]

    bind = await client.put(
        f"/api/v1/test-plans/{plan_id}/case-ids",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "case_ids": [str(case_id)]},
    )
    version = bind.json()["data"]["version"]

    patch = await client.patch(
        f"/api/v1/test-plans/{plan_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "name": "Renamed"},
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["case_ids"] == [str(case_id)]

    detail = await client.get(f"/api/v1/test-plans/{plan_id}")
    assert detail.json()["data"]["name"] == "Renamed"
    assert detail.json()["data"]["case_ids"] == [str(case_id)]
