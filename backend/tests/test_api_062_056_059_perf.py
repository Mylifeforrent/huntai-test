"""Perf run orchestration (FR-11) and PerfBaseline (API-056…059) tests, S-M3-01."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quota_governance.models import OrgQuota
from app.modules.run_orchestration.executor import run_test_run_background
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_admin_peer
from tests.test_run_helpers import activate_platform_executor_env

WHITELIST = ["http://127.0.0.1:9"]
SCENARIO = {
    "users": 1,
    "spawn_rate": 1,
    "run_time_seconds": 2,
    "wait_seconds": 0.1,
}


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 200,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.2)
    raise AssertionError(f"run did not reach {wanted}")


async def create_active_performance_case(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    title: str = "Perf scenario",
) -> dict[str, object]:
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "performance",
            "execution_mode": "script",
            "title": title,
            "drafts": [
                {
                    "steps": [
                        {
                            "action": "request",
                            "params": {"method": "GET", "path": "/pets"},
                        }
                    ],
                    "assertions": [],
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    case_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]
    submit = await client.post(
        f"/api/v1/test-cases/{case_id}/submit-review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    assert submit.status_code == 200, submit.text
    pending_version = submit.json()["data"]["version"]
    approve = await client.post(
        f"/api/v1/test-cases/{case_id}/review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": pending_version, "decision": "approve"},
    )
    assert approve.status_code == 200, approve.text
    return approve.json()["data"]


async def start_perf_run(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    env: dict[str, object],
    case: dict[str, object],
    scenario: dict[str, object] | None = None,
    whitelist: list[str] | None = None,
) -> Any:
    await login_as(client)
    params: dict[str, object] = {
        "TARGET_ENV": "http://127.0.0.1:9",
        "perf_whitelist": WHITELIST if whitelist is None else whitelist,
        "perf_scenario": scenario or SCENARIO,
    }
    return await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "env_id": str(env["id"]),
            "execution_source": "script",
            "case_ids": [str(case["id"])],
            "trigger_type": "manual",
            "expected_env_version": env["version"],
            "params": params,
        },
    )


@pytest.mark.asyncio
async def test_accept_whitelist_denied_no_approval(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    response = await start_perf_run(
        client, project_id=project_id, env=env, case=case, whitelist=["https://other.example"]
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "HT-POL-002"
    # AC-051: 白名单外不进审批
    approvals = await client.get("/api/v1/approval-requests", params={"perspective": "all"})
    assert approvals.status_code == 200
    assert not [
        item
        for item in approvals.json()["data"]["items"]
        if item.get("action_type") == "perf_high_risk"
    ]


@pytest.mark.asyncio
async def test_accept_rejects_mixed_case_types(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    perf_case = await create_active_performance_case(client, project_id=project_id)
    from tests.test_run_helpers import create_active_script_case

    api_case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "env_id": str(env["id"]),
            "execution_source": "script",
            "case_ids": [str(perf_case["id"]), str(api_case["id"])],
            "trigger_type": "manual",
            "expected_env_version": env["version"],
        },
    )
    assert start.status_code == 400
    assert start.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_perf_run_e2e_locust_low_risk(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    start = await start_perf_run(client, project_id=project_id, env=env, case=case)
    assert start.status_code == 200, start.text
    run_id = str(start.json()["data"]["id"])
    run = await _poll_run_status(client, run_id, wanted={"SUCCEEDED"})
    assert run["status"] == "SUCCEEDED"

    results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    assert results.status_code == 200
    items = results.json()["data"]["items"]
    assert items and items[0]["outcome"] == "passed"
    detail = await client.get(f"/api/v1/case-results/{items[0]['id']}")
    artifact_ids = detail.json()["data"]["artifact_ids"]
    assert artifact_ids
    meta = await client.get(f"/api/v1/artifacts/{artifact_ids[0]}")
    assert meta.json()["data"]["kind"] == "perf_report"

    # 并发预算释放
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    quota_row = await db_session.execute(select(OrgQuota).where(OrgQuota.organization_id == org_id))
    quota = quota_row.scalar_one()
    assert quota.perf_concurrency_in_use == 0


@pytest.mark.asyncio
async def test_scenario_mutex_queues_second_run(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    from app.modules.run_orchestration.models import TestRun

    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    # 在途场景 run（模拟施压中）
    now = datetime.now(UTC)
    db_session.add(
        TestRun(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            env_id=uuid.uuid4(),
            execution_source="script",
            trigger_type="manual",
            idempotency_key=str(uuid.uuid4()),
            status="RUNNING",
            snapshot={"case_ids": [str(case["id"])], "params_redacted": {}},
            result_summary={},
        )
    )
    await db_session.commit()
    start = await start_perf_run(client, project_id=project_id, env=env, case=case)
    assert start.status_code == 200, start.text
    run_id = str(start.json()["data"]["id"])
    await _poll_run_status(client, run_id, wanted={"PENDING"})
    await asyncio.sleep(1.0)
    detail = await client.get(f"/api/v1/test-runs/{run_id}")
    assert detail.json()["data"]["status"] == "PENDING"  # 互斥排队，不并行施压

    # 在途 run 终态后晋升
    await db_session.execute(
        update(TestRun)
        .where(TestRun.status == "RUNNING", TestRun.organization_id == org_id)
        .values(status="SUCCEEDED", updated_at=datetime.now(UTC))
    )
    await db_session.commit()
    org_uuid = org_id
    assert isinstance(org_uuid, uuid.UUID)
    await run_test_run_background(organization_id=org_uuid, test_run_id=uuid.UUID(run_id))
    await _poll_run_status(client, run_id, wanted={"SUCCEEDED"})


@pytest.mark.asyncio
async def test_high_risk_scenario_requires_approval_then_resumes(
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
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    scenario = dict(SCENARIO)
    scenario["side_effect_level"] = "L2"
    start = await start_perf_run(
        client, project_id=project_id, env=env, case=case, scenario=scenario
    )
    assert start.status_code == 200, start.text
    run_id = str(start.json()["data"]["id"])
    await _poll_run_status(client, run_id, wanted={"WAITING_APPROVAL"})

    approvals = await client.get("/api/v1/approval-requests", params={"perspective": "all"})
    perf_approvals = [
        item
        for item in approvals.json()["data"]["items"]
        if item.get("action_type") == "perf_high_risk"
    ]
    assert perf_approvals
    approval_id = perf_approvals[0]["id"]
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]

    await login_as(client, idp_subject="admin-peer-120")
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["data"]["status"] == "EXECUTED"
    assert decision.json()["data"]["execution_result"] == "ok"

    run = await _poll_run_status(client, run_id, wanted={"SUCCEEDED"})
    assert run["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_high_risk_rejection_cancels_run(
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
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    scenario = dict(SCENARIO)
    scenario["side_effect_level"] = "L2"
    start = await start_perf_run(
        client, project_id=project_id, env=env, case=case, scenario=scenario
    )
    run_id = str(start.json()["data"]["id"])
    await _poll_run_status(client, run_id, wanted={"WAITING_APPROVAL"})
    approvals = await client.get("/api/v1/approval-requests", params={"perspective": "all"})
    approval_id = next(
        item["id"]
        for item in approvals.json()["data"]["items"]
        if item.get("action_type") == "perf_high_risk"
    )
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await login_as(client, idp_subject="admin-peer-120")
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "reject", "expected_version": version, "reason": "not now"},
    )
    assert decision.status_code == 200, decision.text
    run = await _poll_run_status(client, run_id, wanted={"CANCELLED"})
    assert run["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_quota_exhaustion_fails_run_at_dispatch(
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
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    await db_session.execute(update(OrgQuota).values(perf_concurrency_quota=0))
    await db_session.commit()
    start = await start_perf_run(client, project_id=project_id, env=env, case=case)
    assert start.status_code == 200, start.text
    run_id = str(start.json()["data"]["id"])
    run = await _poll_run_status(client, run_id, wanted={"FAILED"})
    summary = run.get("result_summary")
    assert isinstance(summary, dict)
    assert summary.get("reason") == "perf_quota_exhausted"


@pytest.mark.asyncio
async def test_perf_baseline_crud_and_active_switch(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    _ = env
    case = await create_active_performance_case(client, project_id=project_id)
    case_id = str(case["id"])
    await login_as(client)

    create1 = await client.post(
        "/api/v1/perf-baselines",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "scenario_test_case_id": case_id,
            "metrics_snapshot": {"p95_ms": 120.0},
            "tolerance": {"rt": 0.2},
        },
    )
    assert create1.status_code == 201, create1.text
    baseline1 = create1.json()["data"]
    assert baseline1["is_active"] is True

    listing = await client.get("/api/v1/perf-baselines", params={"scenario_test_case_id": case_id})
    assert listing.status_code == 200
    assert len(listing.json()["data"]["items"]) == 1

    create2 = await client.post(
        "/api/v1/perf-baselines",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "scenario_test_case_id": case_id,
            "metrics_snapshot": {"p95_ms": 100.0},
            "tolerance": {"rt": 0.2},
            "expected_active_version": 1,
        },
    )
    assert create2.status_code == 201, create2.text
    baseline2 = create2.json()["data"]
    assert baseline2["is_active"] is True

    listing = await client.get("/api/v1/perf-baselines", params={"scenario_test_case_id": case_id})
    items = listing.json()["data"]["items"]
    active = [item for item in items if item["is_active"]]
    assert len(active) == 1 and active[0]["id"] == baseline2["id"]

    stale = await client.post(
        "/api/v1/perf-baselines",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "scenario_test_case_id": case_id,
            "metrics_snapshot": {"p95_ms": 90.0},
            "tolerance": {"rt": 0.2},
            "expected_active_version": 2,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "HT-VER-001"

    detail = await client.get(f"/api/v1/perf-baselines/{baseline2['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["comparison"]["baseline_metrics"] == {"p95_ms": 100.0}

    deactivate = await client.post(
        f"/api/v1/perf-baselines/{baseline2['id']}/deactivate",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": baseline2["version"]},
    )
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json()["data"]["is_active"] is False


@pytest.mark.asyncio
async def test_kill_switch_stops_running_load(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    from datetime import timedelta

    from app.modules.identity_tenancy.models import Organization

    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_performance_case(client, project_id=project_id)
    scenario = dict(SCENARIO)
    scenario["run_time_seconds"] = 120  # would run far past the 60s window
    start = await start_perf_run(
        client, project_id=project_id, env=env, case=case, scenario=scenario
    )
    assert start.status_code == 200, start.text
    run_id = str(start.json()["data"]["id"])

    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    tighten = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": org.aggregate_version,
            "target": {"level": "module", "module": "performance"},
            "reason": "kill switch drill",
        },
    )
    assert tighten.status_code == 200, tighten.text

    started_at = datetime.now(UTC)
    run = await _poll_run_status(client, run_id, wanted={"CANCELLED"})
    elapsed = (datetime.now(UTC) - started_at).total_seconds()
    assert run["status"] == "CANCELLED"
    # AC-052: 全部施压进程在 60s 内停止
    assert elapsed < 60.0, f"kill switch took {elapsed}s"
    _ = timedelta
