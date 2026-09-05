"""API-144–146, gate waiver, API-167, API-162 tests for S-M2-03."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates.check_run_stub import CheckRunSyncError
from app.modules.run_orchestration import repository as run_repo
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _start_body
from tests.test_api_120_action_previews import _seed_viewer
from tests.test_api_140_143_quality_gate_policies import THRESHOLDS, _create_body
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case

POLICY_THRESHOLDS = dict(THRESHOLDS)


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 40,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.05)
    raise AssertionError(f"run did not reach {wanted}")


async def _create_quality_gate_policy(
    client: AsyncClient,
    project_id: uuid.UUID,
    *,
    min_pass_rate: float = 100.0,
    mode: str = "report_only",
) -> dict[str, object]:
    await login_as(client)
    thresholds = dict(POLICY_THRESHOLDS)
    thresholds["min_pass_rate"] = min_pass_rate
    response = await client.post(
        "/api/v1/quality-gate-policies",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_create_body(
            project_id,
            mode=mode,
            confirm_blocking=True if mode == "blocking" else None,
            thresholds=thresholds,
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _run_failed_script_case(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    create_policy: bool = True,
    policy_mode: str = "report_only",
) -> dict[str, object]:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    if create_policy:
        await _create_quality_gate_policy(client, project_id, min_pass_rate=100.0, mode=policy_mode)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(
        client,
        project_id=project_id,
        assertions=[{"type": "status_code", "expected": 404}],
    )
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    with patch("app.modules.run_orchestration.executor.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                **_start_body(
                    project_id=project_id,
                    env_id=env["id"],
                    case_ids=[case["id"]],
                    expected_env_version=env["version"],
                ),
                "params": {"TARGET_ENV": "https://example.test"},
            },
        )
    assert start.status_code == 200, start.text
    return await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED"})


@pytest.mark.asyncio
async def test_ac_058_failed_run_creates_fail_evaluation_and_check_run(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _create_quality_gate_policy(client, project_id, mode="blocking")
    run = await _run_failed_script_case(client, db_session, seeded_identity, create_policy=False)
    run_id = str(run["id"])
    assert run.get("gate_evaluation_id") is not None

    gate = await client.get(f"/api/v1/test-runs/{run_id}/gate-evaluation")
    assert gate.status_code == 200
    body = gate.json()["data"]
    assert body["unevaluated_reason"] is None
    assert body["evaluation"] is not None
    assert body["evaluation"]["result"] == "fail"
    assert body["evaluation"]["check_run_ref"]["conclusion"] == "failure"

    listing = await client.get(
        "/api/v1/gate-evaluations",
        params={"project_id": str(project_id)},
    )
    assert listing.status_code == 200
    assert any(item["test_run_id"] == run_id for item in listing.json()["data"]["items"])

    details = body["evaluation"]["threshold_details"]
    assert details["max_p95_ms"]["not_measured"] is True
    assert details["max_error_rate"]["not_measured"] is True


@pytest.mark.asyncio
async def test_agent_run_terminal_has_unevaluated_reason_agent_source(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    now = datetime.now(UTC)
    env_id = uuid.uuid4()
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="agent",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": [], "execution_source": "agent"},
    )
    await db_session.commit()
    await login_as(client)
    gate = await client.get(f"/api/v1/test-runs/{run.id}/gate-evaluation")
    assert gate.status_code == 200
    body = gate.json()["data"]
    assert body["unevaluated_reason"] == "agent_source"
    assert body["evaluation"] is None
    assert body["gate_evaluation_id"] is None

    listing = await client.get(
        "/api/v1/gate-evaluations",
        params={"project_id": str(project_id)},
    )
    assert listing.status_code == 200
    assert all(item["test_run_id"] != str(run.id) for item in listing.json()["data"]["items"])


@pytest.mark.asyncio
async def test_ac_061_cancelled_and_no_policy_skip_evaluation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    now = datetime.now(UTC)
    env_id = uuid.uuid4()

    cancelled = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="CANCELLED",
        snapshot={"case_ids": []},
    )
    no_policy = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": []},
    )
    await db_session.commit()
    await login_as(client)

    cancelled_gate = await client.get(f"/api/v1/test-runs/{cancelled.id}/gate-evaluation")
    assert cancelled_gate.json()["data"]["unevaluated_reason"] == "cancelled_or_timeout"
    assert cancelled_gate.json()["data"]["evaluation"] is None

    no_policy_gate = await client.get(f"/api/v1/test-runs/{no_policy.id}/gate-evaluation")
    assert no_policy_gate.json()["data"]["unevaluated_reason"] == "policy_unmet"
    assert no_policy_gate.json()["data"]["evaluation"] is None
    # 结果枚举仅 pass / fail / waived；未评估不是结果（AC-057/061 纪律）
    assert "not_evaluated" not in cancelled_gate.text
    assert "not_evaluated" not in no_policy_gate.text


@pytest.mark.asyncio
async def test_api_146_running_run_xor_not_terminal(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
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
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="RUNNING",
        snapshot={"case_ids": []},
    )
    await db_session.commit()
    await login_as(client)
    gate = await client.get(f"/api/v1/test-runs/{run.id}/gate-evaluation")
    assert gate.status_code == 200
    body = gate.json()["data"]
    assert body["evaluation"] is None
    assert body["unevaluated_reason"] == "not_terminal"
    assert (body["evaluation"] is None) ^ (body["unevaluated_reason"] is None)


@pytest.mark.asyncio
async def test_ac_060_gate_waiver_requires_confirm_and_approval(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    evaluation_id = gate.json()["data"]["evaluation"]["id"]

    await login_as(client)
    denied = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "action_type": "gate_waiver",
            "project_id": str(project_id),
            "target_object_type": "gate_evaluation",
            "target_object_id": evaluation_id,
            "payload": {},
        },
    )
    assert denied.status_code == 400

    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "action_type": "gate_waiver",
            "project_id": str(project_id),
            "target_object_type": "gate_evaluation",
            "target_object_id": evaluation_id,
            "payload": {"confirm": True},
        },
    )
    assert preview.status_code == 200
    approval_id = preview.json()["data"]["approval_request_id"]
    assert approval_id is not None

    detail_before = await client.get(f"/api/v1/gate-evaluations/{evaluation_id}")
    assert detail_before.json()["data"]["waiver_approval_id"] is None
    assert detail_before.json()["data"]["result"] == "fail"

    await login_as(client, idp_subject="admin-peer-120")
    approval = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = approval.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200

    detail_after = await client.get(f"/api/v1/gate-evaluations/{evaluation_id}")
    assert detail_after.json()["data"]["waiver_approval_id"] == approval_id
    assert detail_after.json()["data"]["result"] == "fail"


@pytest.mark.asyncio
async def test_ac_059_check_run_stub_failure_retries_and_keeps_fail(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    calls = {"count": 0}

    async def flaky_apply_phase(
        ref: dict[str, object],
        *,
        phase: str,
        conclusion: str | None,
        attempt: int,
    ) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] <= 2:
            raise CheckRunSyncError("stub failure")
        ref = dict(ref)
        ref["phases"] = ["queued", "in_progress", "completed"]
        ref["sync_status"] = "completed"
        ref["conclusion"] = conclusion
        ref["attempts"] = attempt
        return ref

    with patch(
        "app.modules.quality_gates.check_run_stub._apply_phase",
        side_effect=flaky_apply_phase,
    ):
        run = await _run_failed_script_case(
            client, db_session, seeded_identity, policy_mode="blocking"
        )

    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    assert gate.json()["data"]["evaluation"]["result"] == "fail"
    assert gate.json()["data"]["evaluation"]["check_run_ref"]["conclusion"] == "failure"

    audit = await client.get("/api/v1/audit-events", params={"project_id": str(project_id)})
    assert audit.status_code == 200
    actions = [item.get("action") for item in audit.json()["data"]["items"]]
    assert "check_run.sync_failed" not in actions or calls["count"] > 2


@pytest.mark.asyncio
async def test_ac_062_patch_policy_does_not_rewrite_historical_evaluation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate_before = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    evaluation = gate_before.json()["data"]["evaluation"]
    evaluation_id = evaluation["id"]
    result_before = evaluation["result"]
    conclusion_before = evaluation["check_run_ref"]["conclusion"]
    assert conclusion_before == "neutral"  # report_only fail 不阻断
    policy_id = evaluation["policy_id"]

    await login_as(client)
    policy_detail = await client.get(f"/api/v1/quality-gate-policies/{policy_id}")
    assert policy_detail.status_code == 200
    patch = await client.patch(
        f"/api/v1/quality-gate-policies/{policy_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": policy_detail.json()["data"]["version"],
            "mode": "blocking",
            "confirm_blocking": True,
        },
    )
    assert patch.status_code == 200

    gate_after = await client.get(f"/api/v1/gate-evaluations/{evaluation_id}")
    assert gate_after.json()["data"]["result"] == result_before
    assert gate_after.json()["data"]["check_run_ref"]["conclusion"] == conclusion_before

    # 切到 blocking 后的新评估用新模式（阻断生效），历史行仍不被改写
    run2 = await _run_failed_script_case(client, db_session, seeded_identity, create_policy=False)
    gate_new = await client.get(f"/api/v1/test-runs/{run2['id']}/gate-evaluation")
    assert gate_new.status_code == 200
    new_evaluation = gate_new.json()["data"]["evaluation"]
    assert new_evaluation is not None
    assert new_evaluation["result"] == "fail"
    assert new_evaluation["check_run_ref"]["conclusion"] == "failure"


@pytest.mark.asyncio
async def test_api_144_illegal_result_query_returns_400(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    response = await client.get(
        "/api/v1/gate-evaluations",
        params={"project_id": str(project_id), "result": "not_evaluated"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_144_unauthenticated_returns_401(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/gate-evaluations?project_id={uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_167_tester_forbidden_owner_put_ok(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    plan_id = uuid.uuid4()
    await _seed_viewer(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client, idp_subject="viewer-120")
    denied = await client.put(
        f"/api/v1/projects/{project_id}/ci-trigger-bindings",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": 1,
            "bindings": [
                {
                    "repository": "org/repo",
                    "ref_pattern": "main",
                    "test_plan_id": str(plan_id),
                }
            ],
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "HT-IAM-001"

    await login_as(client)
    before_runs = await client.get(
        "/api/v1/test-runs",
        params={"project_id": str(project_id)},
    )
    count_before = len(before_runs.json()["data"]["items"])
    allowed = await client.put(
        f"/api/v1/projects/{project_id}/ci-trigger-bindings",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": 1,
            "bindings": [
                {
                    "repository": "org/repo",
                    "ref_pattern": "main",
                    "test_plan_id": str(plan_id),
                }
            ],
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["version"] == 1
    after_runs = await client.get(
        "/api/v1/test-runs",
        params={"project_id": str(project_id)},
    )
    assert len(after_runs.json()["data"]["items"]) == count_before


@pytest.mark.asyncio
async def test_api_162_create_github_connector_no_secrets_in_list(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    _ = seeded_identity
    await login_as(client)
    create = await client.post(
        "/api/v1/connectors",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "type": "github",
            "name": "GitHub CI",
            "auth_method": "hmac",
            "action_contract": {"sideEffectLevel": "L1"},
            "has_credential_binding": True,
        },
    )
    assert create.status_code == 201
    payload = create.json()["data"]
    assert "credential" not in payload
    assert "webhook_secret" not in payload
    assert payload["has_credential"] is True

    listing = await client.get("/api/v1/connectors")
    assert listing.status_code == 200
    item = next(i for i in listing.json()["data"]["items"] if i["id"] == payload["id"])
    assert "credential" not in item
    assert "webhook_secret" not in item
    assert "credential_ref" not in item


@pytest.mark.asyncio
async def test_report_only_fail_records_fail_but_does_not_block(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    run = await _run_failed_script_case(client, db_session, seeded_identity)
    gate = await client.get(f"/api/v1/test-runs/{run['id']}/gate-evaluation")
    assert gate.status_code == 200
    body = gate.json()["data"]
    assert body["unevaluated_reason"] is None
    evaluation = body["evaluation"]
    assert evaluation is not None
    assert evaluation["result"] == "fail"
    # 仅报告模式：如实记录 fail，但 Check Run conclusion=neutral，不阻断 CI
    assert evaluation["check_run_ref"]["conclusion"] == "neutral"
    assert evaluation["policy_snapshot"]["mode"] == "report_only"
