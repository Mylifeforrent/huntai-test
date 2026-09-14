"""API-020 workbench aggregation tests."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy import repository as approval_repo
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.modules.quality_gates import repository as gate_repo
from app.modules.quality_gates.models import GateEvaluation, QualityGatePolicy
from app.modules.run_orchestration import repository as run_repo
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _activate_environment
from tests.test_api_140_143_quality_gate_policies import THRESHOLDS
from tests.test_api_144_146_gate_evaluations import _run_failed_script_case


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


async def _insert_gate_evaluation(
    db_session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    policy_id: uuid.UUID,
    result: str,
    check_run_ref: dict[str, Any] | None = None,
    waiver_approval_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> GateEvaluation:
    now = created_at or datetime.now(UTC)
    row = GateEvaluation(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=now,
        created_by=None,
        test_run_id=test_run_id,
        policy_id=policy_id,
        policy_snapshot={"mode": "report_only"},
        result=result,
        threshold_details={},
        check_run_ref=check_run_ref,
        waiver_approval_id=waiver_approval_id,
        evidence_refs=[],
    )
    await gate_repo.insert_gate_evaluation(db_session, row)
    await db_session.commit()
    return row


async def _seed_terminal_script_run(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    status: str = "FAILED",
    execution_source: str = "script",
) -> uuid.UUID:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    now = datetime.now(UTC)
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source=execution_source,
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status=status,
        snapshot={"case_ids": []},
    )
    await db_session.commit()
    return run.id


async def _seed_quality_gate_policy_row(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> uuid.UUID:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    now = datetime.now(UTC)
    policy_id = uuid.uuid4()
    db_session.add(
        QualityGatePolicy(
            id=policy_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            thresholds=dict(THRESHOLDS),
            mode="report_only",
            scope={},
            policy_version=1,
        )
    )
    await db_session.commit()
    return policy_id


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_fail_evaluation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    evaluation_id = gate.json()["data"]["evaluation"]["id"]

    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = response.json()["data"]["gate_anomalies"]
    match = next(item for item in anomalies if item["test_run_id"] == str(run["id"]))
    assert match["kind"] == "fail_evaluation"
    assert match["gate_evaluation_id"] == evaluation_id
    assert match["result"] == "fail"
    assert match["unevaluated_reason"] is None


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_check_run_failed_is_unique(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    evaluation_id = uuid.UUID(gate.json()["data"]["evaluation"]["id"])
    row = await gate_repo.get_gate_evaluation(
        db_session,
        organization_id=org_id,
        evaluation_id=evaluation_id,
    )
    assert row is not None
    row.check_run_ref = {
        **(row.check_run_ref or {}),
        "sync_status": "failed",
        "conclusion": "failure",
    }
    await db_session.commit()

    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = [
        item
        for item in response.json()["data"]["gate_anomalies"]
        if item["test_run_id"] == str(run["id"])
    ]
    assert len(anomalies) == 1
    assert anomalies[0]["kind"] == "check_run_failed"
    assert anomalies[0]["gate_evaluation_id"] == str(evaluation_id)
    assert anomalies[0]["result"] == "fail"


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_unevaluated_policy_unmet(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    run_id = await _seed_terminal_script_run(db_session, seeded_identity, status="FAILED")
    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = [
        item
        for item in response.json()["data"]["gate_anomalies"]
        if item["test_run_id"] == str(run_id)
    ]
    assert len(anomalies) == 1
    assert anomalies[0]["kind"] == "unevaluated"
    assert anomalies[0]["gate_evaluation_id"] is None
    assert anomalies[0]["result"] is None
    assert anomalies[0]["unevaluated_reason"] == "policy_unmet"


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_pass_without_sync_failed_not_listed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    run_id = await _seed_terminal_script_run(db_session, seeded_identity, status="SUCCEEDED")
    policy_id = await _seed_quality_gate_policy_row(db_session, seeded_identity)
    await _insert_gate_evaluation(
        db_session,
        organization_id=org_id,
        test_run_id=run_id,
        policy_id=policy_id,
        result="pass",
        check_run_ref={"sync_status": "completed", "conclusion": "success"},
    )

    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = response.json()["data"]["gate_anomalies"]
    assert all(item["test_run_id"] != str(run_id) for item in anomalies)


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_waived_not_listed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    evaluation_id = uuid.UUID(gate.json()["data"]["evaluation"]["id"])
    row = await gate_repo.get_gate_evaluation(
        db_session,
        organization_id=org_id,
        evaluation_id=evaluation_id,
    )
    assert row is not None
    row.waiver_approval_id = uuid.uuid4()
    await db_session.commit()

    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = response.json()["data"]["gate_anomalies"]
    assert all(item["test_run_id"] != str(run["id"]) for item in anomalies)


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_agent_run_without_evaluation_not_listed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    run_id = await _seed_terminal_script_run(
        db_session,
        seeded_identity,
        status="FAILED",
        execution_source="agent",
    )
    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = response.json()["data"]["gate_anomalies"]
    assert all(item["test_run_id"] != str(run_id) for item in anomalies)


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_cross_tenant_not_visible(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    other_project = uuid.uuid4()
    policy_id = uuid.uuid4()
    evaluation_id = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Foreign Org",
            slug="foreign-workbench-gate",
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
            idp_subject="foreign-workbench-gate",
            display_name="Foreign",
            email="foreign-workbench@example.com",
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
    foreign_run = await run_repo.create_test_run(
        db_session,
        organization_id=other_org,
        created_at=now,
        created_by=other_user,
        project_id=other_project,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": []},
    )
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
    await db_session.flush()
    db_session.add(
        GateEvaluation(
            id=evaluation_id,
            organization_id=other_org,
            created_at=now,
            created_by=other_user,
            test_run_id=foreign_run.id,
            policy_id=policy_id,
            policy_snapshot={"mode": "report_only"},
            result="fail",
            threshold_details={},
            check_run_ref={"sync_status": "completed"},
            waiver_approval_id=None,
            evidence_refs=[],
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get("/api/v1/workbench")
    assert response.status_code == 200
    anomalies = response.json()["data"]["gate_anomalies"]
    assert all(item["gate_evaluation_id"] != str(evaluation_id) for item in anomalies)


@pytest.mark.asyncio
async def test_api_020_gate_anomaly_project_id_filter(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    project_a = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(project_a, uuid.UUID)
    now = datetime.now(UTC)
    project_b = uuid.uuid4()
    db_session.add(
        Project(
            id=project_b,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            name="Project B",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_b,
            user_id=user_id,
            role="owner",
        )
    )
    await db_session.flush()
    run_a = await _seed_terminal_script_run(db_session, seeded_identity, status="FAILED")
    run_b = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_b,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": []},
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get(f"/api/v1/workbench?project_id={project_a}")
    assert response.status_code == 200
    run_ids = {item["test_run_id"] for item in response.json()["data"]["gate_anomalies"]}
    assert str(run_a) in run_ids
    assert str(run_b.id) not in run_ids
