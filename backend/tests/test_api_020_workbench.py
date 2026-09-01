"""API-020 workbench aggregation tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy import repository as approval_repo
from app.modules.identity_tenancy.models import ProjectMember, User
from app.modules.run_orchestration import repository as run_repo
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _activate_environment


async def _seed_tester(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "tester-workbench",
) -> uuid.UUID:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject=idp_subject,
            display_name="Tester",
            email=f"{idp_subject}@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role="tester",
        )
    )
    await db_session.commit()
    return user_id


@pytest.mark.asyncio
async def test_api_020_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_020_happy_path_four_keys(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    now = datetime.now(UTC)
    await approval_repo.create_approval_request(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        action_type="jira_write",
        target_object_type="TestRun",
        target_object_id=uuid.uuid4(),
        action_payload={"summary": "test"},
        param_hash="hash-workbench",
        card_payload={"action": "write"},
        side_effect_level="L2",
        initiator_id=user_id,
        approver_id=user_id,
        expires_at=now + timedelta(hours=2),
        project_id=project_id,
    )

    env = await _activate_environment(client, db_session, seeded_identity)
    waiting_since = now - timedelta(seconds=90)
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=waiting_since,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(env["id"]),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_APPROVAL",
        snapshot={
            "case_ids": [str(uuid.uuid4())],
            "env_id": env["id"],
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    run.updated_at = waiting_since
    await db_session.commit()

    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "pending_approvals" in data
    assert "active_runs" in data
    assert "gate_anomalies" in data
    assert "quota" in data
    assert data["gate_anomalies"] == []
    assert len(data["pending_approvals"]) >= 1
    assert len(data["active_runs"]) >= 1

    waiting = next(item for item in data["active_runs"] if item["status"] == "WAITING_APPROVAL")
    assert waiting["dwell_seconds"] >= 90


@pytest.mark.asyncio
async def test_api_020_unknown_project_id_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    unknown = uuid.uuid4()
    response = await client.get(f"/api/v1/workbench?project_id={unknown}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_020_tester_can_read(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_tester(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client, idp_subject="tester-workbench")
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data["pending_approvals"], list)
    assert isinstance(data["active_runs"], list)
