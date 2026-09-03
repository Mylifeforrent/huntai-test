"""S-M1-05 external_ci Jenkins trigger + JUnit collection tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import query_port as execution_query
from app.modules.run_orchestration import repository as run_repo
from app.modules.run_orchestration.external_ci_executor import execute_external_ci_run
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _start_body
from tests.test_api_090_160_164_106_integration import _github_signature, _seed_connector
from tests.test_api_170_172_api_tokens import _issue_body
from tests.test_run_helpers import (
    activate_external_ci_env,
    create_active_referenced_case,
)

JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="suite">
  <testcase classname="c" name="test_ok"/>
  <testcase classname="c" name="test_fail"><failure message="boom"/></testcase>
</testsuite>
"""


class _JenkinsMockClient:
    def __init__(self, *, job_exists: bool = True, trigger_ok: bool = True) -> None:
        self.job_exists = job_exists
        self.trigger_ok = trigger_ok
        self.get = AsyncMock(side_effect=self._get)
        self.post = AsyncMock(side_effect=self._post)

    async def _get(self, url: str, **kwargs: object) -> Response:
        _ = kwargs
        path = url.split("?", 1)[0]
        if "/queue/item/" in path:
            return Response(200, json={"executable": {"number": 42}})
        if "/artifact/" in path:
            return Response(200, text=JUNIT_XML)
        if "/lastBuild/" in path:
            return Response(200, json={"number": 42, "building": False, "result": "FAILURE"})
        if "/job/smoke-suite/" in path and path.rstrip("/").endswith("/api/json"):
            remainder = path.split("/job/smoke-suite/", 1)[1]
            if remainder == "api/json":
                if not self.job_exists:
                    return Response(404, json={"message": "not found"})
                return Response(200, json={"buildable": True})
            return Response(200, json={"building": False, "result": "FAILURE"})
        return Response(404, text="unexpected")

    async def _post(self, url: str, **kwargs: object) -> Response:
        _ = kwargs
        if "buildWithParameters" in url or url.rstrip("/").endswith("/build"):
            if not self.trigger_ok:
                return Response(500, text="error")
            return Response(
                201,
                headers={"Location": "https://ci.example.com/queue/item/123/"},
                text="",
            )
        return Response(404, text="unexpected")


def _jenkins_mock_client(*, job_exists: bool = True, trigger_ok: bool = True) -> _JenkinsMockClient:
    return _JenkinsMockClient(job_exists=job_exists, trigger_ok=trigger_ok)


async def _poll_run(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 60,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.05)
    raise AssertionError(f"run {run_id} did not reach {wanted}")


@pytest.mark.asyncio
async def test_schema_fail_no_jenkins_post(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    await login_as(client)
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                **_start_body(
                    project_id=project_id,
                    env_id=env["id"],
                    case_ids=[case["id"]],
                    execution_source="external_ci",
                    expected_env_version=env["version"],
                ),
                "params": {},
            },
        )
        assert start.status_code == 200
        detail = await _poll_run(client, start.json()["data"]["id"], wanted={"FAILED"})
    assert detail["result_summary"]["reason"] == "params_schema_invalid"
    assert mock_client.post.await_count == 0


@pytest.mark.asyncio
async def test_job_404_invalidates_case_no_trigger(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    await login_as(client)
    mock_client = _jenkins_mock_client(job_exists=False)
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                **_start_body(
                    project_id=project_id,
                    env_id=env["id"],
                    case_ids=[case["id"]],
                    execution_source="external_ci",
                    expected_env_version=env["version"],
                ),
                "params": {"branch": "main"},
            },
        )
        assert start.status_code == 200
        await _poll_run(client, start.json()["data"]["id"], wanted={"FAILED"})
    case_detail = await client.get(f"/api/v1/test-cases/{case['id']}")
    assert case_detail.json()["data"]["validity"] == "invalid"
    assert mock_client.post.await_count == 0


@pytest.mark.asyncio
async def test_happy_path_trigger_once_and_junit(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    await login_as(client)
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                **_start_body(
                    project_id=project_id,
                    env_id=env["id"],
                    case_ids=[case["id"]],
                    execution_source="external_ci",
                    expected_env_version=env["version"],
                ),
                "params": {"branch": "main"},
            },
        )
        assert start.status_code == 200
        run_id = start.json()["data"]["id"]
        detail = await _poll_run(
            client,
            run_id,
            wanted={"SUCCEEDED", "FAILED", "WAITING_EXTERNAL", "RUNNING"},
        )
        if detail["status"] not in {"SUCCEEDED", "FAILED"}:
            detail = await _poll_run(client, run_id, wanted={"SUCCEEDED", "FAILED"})
    assert mock_client.post.await_count == 1
    results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    assert results.status_code == 200
    assert len(results.json()["data"]["items"]) >= 1


@pytest.mark.asyncio
async def test_replay_same_idempotency_key_one_post(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    await login_as(client)
    key = str(uuid.uuid4())
    body = {
        **_start_body(
            project_id=project_id,
            env_id=env["id"],
            case_ids=[case["id"]],
            execution_source="external_ci",
            expected_env_version=env["version"],
        ),
        "params": {"branch": "main"},
    }
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        first = await client.post("/api/v1/test-runs", headers={"Idempotency-Key": key}, json=body)
        second = await client.post("/api/v1/test-runs", headers={"Idempotency-Key": key}, json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    await _poll_run(client, first.json()["data"]["id"], wanted={"SUCCEEDED", "FAILED"})
    assert mock_client.post.await_count == 1


@pytest.mark.asyncio
async def test_executor_replay_triggered_skips_second_post(
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
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    env_info = await execution_query.get_environment_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
    )
    assert env_info is not None
    contract = await execution_query.get_job_contract_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
        job_id="smoke-suite",
    )
    assert contract is not None
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(str(env["id"])),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_EXTERNAL",
        snapshot={
            "case_ids": [case["id"]],
            "env_id": env["id"],
            "params_redacted": {"branch": "main"},
            "execution_source": "external_ci",
            "trigger_type": "manual",
        },
    )
    run.result_summary = {
        "ci": {
            "trigger_state": "triggered",
            "job_id": "smoke-suite",
            "build_number": 42,
            "queue_url": "https://ci.example.com/queue/item/123/",
        }
    }
    await db_session.commit()
    contracts = [
        {
            "case": {"id": case["id"], "version_id": case.get("current_version_id")},
            "contract": contract,
            "job_id": "smoke-suite",
        }
    ]
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        await execute_external_ci_run(
            organization_id=org_id,
            test_run_id=run.id,
            contracts=contracts,
            env_info=env_info,
        )
    assert mock_client.post.await_count == 0


@pytest.mark.asyncio
async def test_execution_result_unknown_skips_second_post(
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
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    env_info = await execution_query.get_environment_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
    )
    assert env_info is not None
    contract = await execution_query.get_job_contract_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
        job_id="smoke-suite",
    )
    assert contract is not None
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(str(env["id"])),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_EXTERNAL",
        snapshot={"case_ids": [case["id"]], "params_redacted": {"branch": "main"}},
    )
    run.result_summary = {
        "ci": {
            "trigger_state": "pending",
            "execution_result": "unknown",
            "job_id": "smoke-suite",
        }
    }
    await db_session.commit()
    contracts = [{"case": {"id": case["id"]}, "contract": contract, "job_id": "smoke-suite"}]
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        await execute_external_ci_run(
            organization_id=org_id,
            test_run_id=run.id,
            contracts=contracts,
            env_info=env_info,
        )
    assert mock_client.post.await_count == 0
    refreshed = await run_repo.get_test_run(db_session, organization_id=org_id, test_run_id=run.id)
    assert refreshed is not None
    assert refreshed.status == "WAITING_EXTERNAL"


@pytest.mark.asyncio
async def test_api_090_ci_hmac_fail_and_ok(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    connector_id = await _seed_connector(
        db_session,
        org_id=org_id,
        connector_type="ci",
        name="Jenkins",
        webhook_secret_ref="env:JENKINS_WEBHOOK_SECRET",
    )
    body = json.dumps({"name": "smoke-suite", "build": {"number": 1, "phase": "STARTED"}}).encode()
    bad = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "HT-AUTH-004"
    ok = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body, "test-jenkins-webhook-secret"),
        },
    )
    assert ok.status_code in {200, 202}
    dup = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body, "test-jenkins-webhook-secret"),
        },
    )
    assert dup.status_code == 200
    assert dup.json()["data"]["duplicate"] is True


@pytest.mark.asyncio
async def test_api_080_external_ci_execute_scope(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    await login_as(client)
    issue = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["execute"]),
    )
    token = issue.json()["data"]["token"]
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "project_id": str(project_id),
                "env_id": env["id"],
                "execution_source": "external_ci",
                "case_ids": [case["id"]],
                "expected_env_version": env["version"],
                "params": {"branch": "main"},
            },
        )
    assert start.status_code == 200


@pytest.mark.asyncio
async def test_waiting_external_cancel(
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
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(str(env["id"])),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_EXTERNAL",
        snapshot={"case_ids": [case["id"]], "params_redacted": {"branch": "main"}},
    )
    run.result_summary = {
        "ci": {"trigger_state": "triggered", "job_id": "smoke-suite", "build_number": 42},
    }
    await db_session.commit()
    await login_as(client)
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        cancel = await client.post(
            f"/api/v1/test-runs/{run.id}/cancel",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={"expected_version": run.aggregate_version},
        )
    assert cancel.status_code == 200
    assert cancel.json()["data"]["test_run"]["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_pending_trigger_skips_second_post(
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
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    env_info = await execution_query.get_environment_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
    )
    assert env_info is not None
    contract = await execution_query.get_job_contract_for_run(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
        job_id="smoke-suite",
    )
    assert contract is not None
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(str(env["id"])),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_EXTERNAL",
        snapshot={"case_ids": [case["id"]], "params_redacted": {"branch": "main"}},
    )
    run.result_summary = {
        "ci": {
            "trigger_state": "pending",
            "job_id": "smoke-suite",
        }
    }
    await db_session.commit()
    contracts = [{"case": {"id": case["id"]}, "contract": contract, "job_id": "smoke-suite"}]
    mock_client = _jenkins_mock_client()
    with patch("app.modules.run_orchestration.external_ci_executor.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        await execute_external_ci_run(
            organization_id=org_id,
            test_run_id=run.id,
            contracts=contracts,
            env_info=env_info,
        )
    assert mock_client.post.await_count == 0


@pytest.mark.asyncio
async def test_cross_tenant_run_get_not_found(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    from datetime import UTC, datetime

    from app.modules.run_orchestration.models import TestRun

    _ = seeded_identity
    now = datetime.now(UTC)
    run = TestRun(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        created_by=None,
        aggregate_version=1,
        project_id=uuid.uuid4(),
        env_id=uuid.uuid4(),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="RUNNING",
        snapshot={},
        result_summary={},
    )
    db_session.add(run)
    await db_session.commit()
    await login_as(client)
    response = await client.get(f"/api/v1/test-runs/{run.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
