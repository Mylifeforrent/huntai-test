"""API-067/068 and agent worker tests (S-M2-07, FR-19 M2 pilot)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.run_orchestration.agent_worker import run_agent_worker
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _start_body
from tests.test_run_helpers import activate_platform_executor_env

MANIFEST = {
    "allowed_tools": ["request"],
    "max_steps": 10,
    "total_timeout_seconds": 30,
}


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 120,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.1)
    raise AssertionError(f"run did not reach {wanted}")


async def create_active_agent_case(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "agent",
            "title": "Agent case",
            "drafts": [
                {
                    "steps": steps
                    or [
                        {
                            "action": "request",
                            "params": {
                                "method": "GET",
                                "path": "/pets",
                                "side_effect_level": "L0",
                            },
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


async def start_agent_run(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    env: dict[str, object],
    case: dict[str, object],
    params: dict[str, object] | None = None,
) -> str:
    await login_as(client)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(
            project_id=project_id,
            env_id=str(env["id"]),
            case_ids=[str(case["id"])],
            execution_source="agent",
            expected_env_version=int(env["version"]),  # type: ignore[arg-type]
        )
        | {"params": params or {"TARGET_ENV": "http://127.0.0.1:9", "agent_manifest": MANIFEST}},
    )
    assert start.status_code == 200, start.text
    return str(start.json()["data"]["id"])


def worker_payload(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    case: dict[str, object],
    params: dict[str, object],
    manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "organization_id": str(organization_id),
        "test_run_id": str(test_run_id),
        "created_by": None,
        "cases": [case],
        "params": params,
        "manifest": manifest or MANIFEST,
        "base_url": str(params.get("TARGET_ENV", "")),
    }


@pytest.mark.asyncio
async def test_api_067_non_agent_run(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from app.modules.run_orchestration.models import TestRun

    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    now = datetime.now(UTC)
    run = TestRun(
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
        status="SUCCEEDED",
        snapshot={"case_ids": []},
        result_summary={},
    )
    db_session.add(run)
    await db_session.commit()
    await login_as(client)
    response = await client.get(f"/api/v1/test-runs/{run.id}/trajectory")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["available"] is False
    assert data["unavailable_reason"] == "not_agent_source"


@pytest.mark.asyncio
async def test_api_067_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    _ = seeded_identity
    response = await client.get(f"/api/v1/test-runs/{uuid.uuid4()}/trajectory")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_agent_run_e2e_trajectory_and_draft(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_agent_case(client, project_id=project_id)
    run_id = await start_agent_run(client, project_id=project_id, env=env, case=case)
    run = await _poll_run_status(client, run_id, wanted={"FAILED"})

    trajectory = await client.get(f"/api/v1/test-runs/{run_id}/trajectory")
    assert trajectory.status_code == 200
    data = trajectory.json()["data"]
    assert data["available"] is True
    a8 = data["a8"]
    assert a8["status"] == "completed"
    assert a8["incomplete"] is False
    step = a8["steps"][0]
    assert step["action"]["tool"] == "request"
    assert step["action"]["args_hash"]
    # 脱敏：参数原文不得出现在轨迹投影
    assert "/pets" not in trajectory.text

    run_detail = await client.get(f"/api/v1/test-runs/{run_id}")
    assert run_detail.json()["data"]["status"] == "FAILED"
    assert "case_results" in str(run["status"]) or run["status"] == "FAILED"

    draft = await client.post(
        f"/api/v1/test-runs/{run_id}/script-drafts",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert draft.status_code == 200, draft.text
    test_case = draft.json()["data"]["test_case"]
    assert test_case["lifecycle_status"] == "DRAFT"
    assert test_case["execution_mode"] == "script"
    assert "ai-generated" in test_case["tags"]
    assert draft.json()["data"]["test_run_id"] == run_id
    # 原 run 状态不变
    assert (await client.get(f"/api/v1/test-runs/{run_id}")).json()["data"]["status"] == "FAILED"

    replay = await client.post(
        f"/api/v1/test-runs/{run_id}/script-drafts",
        headers={"Idempotency-Key": "not-a-uuid"},
        json={},
    )
    assert replay.status_code == 400


@pytest.mark.asyncio
async def test_agent_worker_happy_and_denies(
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

    await login_as(client)

    async def _seed_running_run(manifest: dict[str, object]) -> tuple[TestRun, dict[str, object]]:
        now = datetime.now(UTC)
        run = TestRun(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            env_id=uuid.uuid4(),
            execution_source="agent",
            trigger_type="manual",
            idempotency_key=str(uuid.uuid4()),
            status="RUNNING",
            snapshot={"case_ids": []},
            result_summary={},
        )
        db_session.add(run)
        await db_session.commit()
        case_payload: dict[str, object] = {
            "id": str(uuid.uuid4()),
            "steps": [
                {
                    "action": "request",
                    "params": {"method": "GET", "path": "/x", "side_effect_level": "L0"},
                }
            ]
            * 3,
            "assertions": [{"type": "status_code", "expected": 200}],
        }
        params: dict[str, object] = {"TARGET_ENV": "http://unit-test", "agent_manifest": manifest}
        return run, worker_payload(
            organization_id=org_id,
            test_run_id=run.id,
            case=case_payload,
            params=params,
            manifest=manifest,
        )

    # Happy path: mocked request succeeds, assertion passes → SUCCEEDED.
    run, payload = await _seed_running_run(MANIFEST)
    with patch(
        "app.modules.run_orchestration.agent_worker.execute_request_step",
        new_callable=AsyncMock,
        return_value={"ok": True, "status_code": 200, "elapsed_ms": 5},
    ):
        await run_agent_worker(payload)
    await db_session.rollback()
    await db_session.refresh(run)
    assert run.status == "SUCCEEDED"
    trajectory = await client.get(f"/api/v1/test-runs/{run.id}/trajectory")
    assert trajectory.status_code == 200
    a8 = trajectory.json()["data"]["a8"]
    assert a8["status"] == "completed"
    assert a8["assertion_results"][0]["passed"] is True

    # Whitelist denies: 3 consecutive DENY → auto terminate (AC-085).
    run2, payload2 = await _seed_running_run(
        {"allowed_tools": ["other_tool"], "max_steps": 10, "total_timeout_seconds": 30}
    )
    await run_agent_worker(payload2)
    await db_session.rollback()
    await db_session.refresh(run2)
    assert run2.status == "CANCELLED"
    trajectory2 = await client.get(f"/api/v1/test-runs/{run2.id}/trajectory")
    a8_2 = trajectory2.json()["data"]["a8"]
    assert a8_2["status"] == "incomplete"
    assert a8_2["incomplete"] is True
    assert len(trajectory2.json()["data"]["policy_denials"]) == 3

    # max_steps=1 with 2 steps → incomplete + CANCELLED (AC-083), no auto retry.
    run3, payload3 = await _seed_running_run(
        {"allowed_tools": ["request"], "max_steps": 1, "total_timeout_seconds": 30}
    )
    with patch(
        "app.modules.run_orchestration.agent_worker.execute_request_step",
        new_callable=AsyncMock,
        return_value={"ok": True, "status_code": 200, "elapsed_ms": 5},
    ):
        await run_agent_worker(payload3)
    await db_session.rollback()
    await db_session.refresh(run3)
    assert run3.status == "CANCELLED"
    trajectory3 = await client.get(f"/api/v1/test-runs/{run3.id}/trajectory")
    a8_3 = trajectory3.json()["data"]["a8"]
    assert a8_3["status"] == "incomplete"
    assert len(a8_3["steps"]) == 1


@pytest.mark.asyncio
async def test_api_068_state_and_role_errors(
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
    from app.modules.identity_tenancy.models import ProjectMember, User
    from app.modules.results_evidence import object_store
    from app.modules.results_evidence.command_port import ArtifactWrite, append_artifact
    from app.modules.run_orchestration.models import TestRun

    now = datetime.now(UTC)
    run = TestRun(
        id=uuid.uuid4(),
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        project_id=project_id,
        env_id=uuid.uuid4(),
        execution_source="agent",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="SUCCEEDED",
        snapshot={"case_ids": []},
        result_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    # 无轨迹 → HT-STATE-001
    await login_as(client)
    no_trajectory = await client.post(
        f"/api/v1/test-runs/{run.id}/script-drafts",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert no_trajectory.status_code == 409
    assert no_trajectory.json()["error"]["code"] == "HT-STATE-001"

    # incomplete 轨迹 → HT-STATE-001（fail-close 拒绝转换）
    trajectory_payload: dict[str, object] = {
        "task_id": str(run.id),
        "status": "incomplete",
        "steps": [],
        "assertion_results": [],
        "token_usage": {},
        "incomplete": True,
        "executed_steps": [],
        "meta": {"assertions": []},
    }
    artifact_id = uuid.uuid4()
    object_key = object_store.generate_object_key(
        organization_id=org_id, artifact_id=artifact_id, filename="trajectory.json"
    )
    import json as _json

    checksum = object_store.write_bytes(
        object_key=object_key,
        data=_json.dumps(trajectory_payload).encode("utf-8"),
    )
    await append_artifact(
        db_session,
        organization_id=org_id,
        created_by=user_id,
        created_at=now,
        payload=ArtifactWrite(
            test_run_id=run.id,
            kind="agent_trajectory",
            object_key=object_key,
            checksum=checksum,
            byte_size=0,
            mime_type="application/json",
            data_classification="Internal",
            original_filename="trajectory.json",
            artifact_id=artifact_id,
        ),
    )
    await db_session.commit()
    incomplete = await client.post(
        f"/api/v1/test-runs/{run.id}/script-drafts",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["error"]["code"] == "HT-STATE-001"

    # viewer → HT-IAM-001（fail-close）
    viewer = User(
        id=uuid.uuid4(),
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        idp_subject="agent-viewer",
        display_name="Viewer",
        email="agent-viewer@example.com",
        is_disabled=False,
    )
    db_session.add(viewer)
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
            user_id=viewer.id,
            role="viewer",
        )
    )
    await db_session.commit()
    await login_as(client, idp_subject="agent-viewer")
    forbidden_response = await client.post(
        f"/api/v1/test-runs/{run.id}/script-drafts",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error"]["code"] == "HT-IAM-001"
