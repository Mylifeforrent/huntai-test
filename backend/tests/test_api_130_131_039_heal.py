"""API-130/131, heal_apply, API-039 tests for S-M1-03."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeOutput
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _start_body
from tests.test_api_120_action_previews import _preview_body, _seed_viewer
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case


async def _poll_run_status(
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
    raise AssertionError(f"run did not reach {wanted}")


async def _poll_cluster_report(
    client: AsyncClient,
    run_id: str,
    *,
    wanted_status: set[str],
    max_attempts: int = 60,
) -> dict[str, Any]:
    for _ in range(max_attempts):
        response = await client.get(f"/api/v1/test-runs/{run_id}/failure-clusters")
        assert response.status_code == 200
        payload = response.json()["data"]
        if payload.get("generation_status") in wanted_status:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError(f"cluster report did not reach {wanted_status}")


async def _start_failed_run(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    status_code: int = 500,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from unittest.mock import AsyncMock

    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(
        client,
        project_id=project_id,
        assertions=[{"type": "status_code", "expected": 200}],
    )
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_response.text = '{"error":"boom"}'
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
    assert start.status_code == 200
    run = await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED"})
    report = await _poll_cluster_report(
        client,
        run["id"],
        wanted_status={"ready", "degraded"},
    )
    return run, report


def _ok_invoke(clusters_payload: dict[str, Any]):
    async def _mock_invoke(session: object, request: object) -> InvokeOutput:
        _ = session
        _ = request
        return InvokeOutput(
            log_id=uuid.uuid4(),
            result="ok",
            model="test-model",
            usage={"structured_output": clusters_payload},
            cost=Decimal("0"),
            latency_ms=1,
            data_classification="Confidential",
        )

    return _mock_invoke


@pytest.mark.asyncio
async def test_no_failed_cases_empty_cluster_report(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from unittest.mock import AsyncMock

    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
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
    run = await _poll_run_status(client, start.json()["data"]["id"], wanted={"SUCCEEDED"})
    report = await _poll_cluster_report(client, run["id"], wanted_status={"ready"})
    assert report["items"] == []
    assert report["unclustered_refs"] == []
    assert report["generation_status"] == "ready"
    assert report["degraded"] is False


@pytest.mark.asyncio
async def test_rule_fallback_degraded_confidence_03(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity, status_code=500)
    assert report["degraded"] is True
    assert report["generation_status"] == "degraded"
    assert report["items"]
    assert report["items"][0]["confidence"] == 0.3
    assert report["items"][0]["category"] in {
        "env_down",
        "auth_expired",
        "locator_stale",
        "assertion_real_bug",
        "flaky",
        "data_issue",
        "unknown",
    }


@pytest.mark.asyncio
async def test_mock_invoke_ok_clusters_and_fixes(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from unittest.mock import AsyncMock

    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await create_active_script_case(client, project_id=project_id)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.text = '{"error":"boom"}'
    mock_response.headers = {}
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    async def _start_and_capture_case_result() -> tuple[dict[str, Any], str]:
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
        run = await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED"})
        case_results = await client.get(f"/api/v1/test-runs/{run['id']}/case-results")
        return run, case_results.json()["data"]["items"][0]["id"]

    with patch("app.modules.run_orchestration.executor.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_client
        run, case_result_id = await _start_and_capture_case_result()

    clusters_payload = {
        "clusters": [
            {
                "cluster_id": "c1",
                "failure_refs": [case_result_id],
                "category": "assertion_real_bug",
                "root_cause": "status mismatch",
                "confidence": 0.85,
                "evidence_refs": [],
                "blocking_judgment": "blocker",
                "suggested_actions": [],
                "can_auto_apply": False,
                "fixes": [
                    {
                        "field": "assertions",
                        "current": "200",
                        "suggested": '{"assertions":[{"type":"status_code","expected":500}]}',
                        "reason": "align expected",
                        "confidence": 0.85,
                    }
                ],
            }
        ],
        "unclustered_refs": [],
        "meta": {"prompt_version": "prompt/failure-triage@1.0.0", "model": "test"},
    }
    from sqlalchemy import delete

    from app.modules.results_evidence.command_port import run_failure_triage_background
    from app.modules.results_evidence.models import FailureCluster

    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    await db_session.execute(
        delete(FailureCluster).where(
            FailureCluster.organization_id == org_id,
            FailureCluster.test_run_id == uuid.UUID(str(run["id"])),
        )
    )
    from app.modules.run_orchestration import command_port as run_command

    await run_command.merge_clustering_projection(
        db_session,
        organization_id=org_id,
        test_run_id=uuid.UUID(str(run["id"])),
        clustering={"generation_status": "pending", "degraded": False, "unclustered_refs": []},
    )
    await db_session.commit()
    with patch("app.modules.results_evidence.a2_service.invoke", new=_ok_invoke(clusters_payload)):
        await run_failure_triage_background(
            organization_id=org_id,
            test_run_id=uuid.UUID(str(run["id"])),
        )
    await login_as(client)
    report = await client.get(f"/api/v1/test-runs/{run['id']}/failure-clusters")
    assert report.status_code == 200
    data = report.json()["data"]
    assert data["degraded"] is False
    assert data["items"][0]["confidence"] == 0.85
    cluster_id = data["items"][0]["id"]
    detail = await client.get(f"/api/v1/failure-clusters/{cluster_id}")
    assert detail.status_code == 200
    fixes = detail.json()["data"]["fixes_preview"]
    assert fixes[0]["confidence"] == 0.85
    assert fixes[0]["can_auto_apply"] is False


@pytest.mark.asyncio
async def test_ac_028_preview_heal_low_confidence_rejected(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            target_id=uuid.UUID(str(case["id"])),
            action_type="heal_apply",
            payload={
                "failure_cluster_id": str(uuid.uuid4()),
                "cluster_confidence": 0.2,
                "fix_confidence": 0.2,
                "patch": {"assertions": []},
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": case["version"],
            },
        ),
    )
    assert preview.status_code == 403


@pytest.mark.asyncio
async def test_token_on_api_130_returns_401(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from tests.test_api_170_172_api_tokens import _issue_body

    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    token_resp = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["read"]),
    )
    token = token_resp.json()["data"]["token"]
    client.cookies.clear()
    response = await client.get(
        "/api/v1/test-runs/00000000-0000-0000-0000-000000000001/failure-clusters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_second_triage_does_not_duplicate_clusters(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    first_count = len(report["items"])
    from app.modules.results_evidence.command_port import run_failure_triage_background

    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    await run_failure_triage_background(
        organization_id=org_id,
        test_run_id=uuid.UUID(str(_run["id"])),
    )
    await login_as(client)
    second = await client.get(f"/api/v1/test-runs/{_run['id']}/failure-clusters")
    assert len(second.json()["data"]["items"]) == first_count


async def _failed_run_with_high_confidence_cluster(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run, _report = await _start_failed_run(client, db_session, seeded_identity)
    case_results = await client.get(f"/api/v1/test-runs/{run['id']}/case-results")
    case_item = case_results.json()["data"]["items"][0]
    case_result_id = case_item["id"]
    case_resp = await client.get(f"/api/v1/test-cases/{case_item['test_case_id']}")
    assert case_resp.status_code == 200
    case = case_resp.json()["data"]
    clusters_payload = {
        "clusters": [
            {
                "cluster_id": "c1",
                "failure_refs": [case_result_id],
                "category": "assertion_real_bug",
                "root_cause": "status mismatch",
                "confidence": 0.85,
                "evidence_refs": [],
                "blocking_judgment": "blocker",
                "fixes": [
                    {
                        "field": "assertions",
                        "current": "200",
                        "suggested": '{"assertions":[{"type":"status_code","expected":500}]}',
                        "reason": "align",
                        "confidence": 0.85,
                    }
                ],
            }
        ],
        "unclustered_refs": [],
    }
    from sqlalchemy import delete

    from app.modules.results_evidence.command_port import run_failure_triage_background
    from app.modules.results_evidence.models import FailureCluster
    from app.modules.run_orchestration import command_port as run_command

    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    await db_session.execute(
        delete(FailureCluster).where(
            FailureCluster.organization_id == org_id,
            FailureCluster.test_run_id == uuid.UUID(str(run["id"])),
        )
    )
    await run_command.merge_clustering_projection(
        db_session,
        organization_id=org_id,
        test_run_id=uuid.UUID(str(run["id"])),
        clustering={"generation_status": "pending", "degraded": False, "unclustered_refs": []},
    )
    await db_session.commit()
    with patch("app.modules.results_evidence.a2_service.invoke", new=_ok_invoke(clusters_payload)):
        await run_failure_triage_background(
            organization_id=org_id,
            test_run_id=uuid.UUID(str(run["id"])),
        )
    await login_as(client)
    report = await client.get(f"/api/v1/test-runs/{run['id']}/failure-clusters")
    return run, case, report.json()["data"]


@pytest.mark.asyncio
async def test_heal_apply_success_does_not_change_test_run_status(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    run, case, report = await _failed_run_with_high_confidence_cluster(
        client, db_session, seeded_identity
    )
    cluster_id = report["items"][0]["id"]
    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            target_id=uuid.UUID(str(case["id"])),
            action_type="heal_apply",
            payload={
                "failure_cluster_id": cluster_id,
                "cluster_confidence": 0.85,
                "fix_confidence": 0.85,
                "patch": {"assertions": [{"type": "status_code", "expected": 500}]},
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": case["version"],
            },
        ),
    )
    assert preview.status_code == 200
    approval_id = preview.json()["data"]["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    await login_as(client)
    run_after = await client.get(f"/api/v1/test-runs/{run['id']}")
    assert run_after.json()["data"]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_api_039_rollback_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange

    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_script_case(client, project_id=project_id)
    await _seed_viewer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
        idp_subject="viewer-039",
    )
    await login_as(client, idp_subject="viewer-039")
    response = await client.post(
        f"/api/v1/test-cases/{case['id']}/rollback",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": case["version"],
            "target_version_id": case["current_version_id"],
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ac_029_heal_execute_stale_version_failed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    _run, case, report = await _failed_run_with_high_confidence_cluster(
        client, db_session, seeded_identity
    )
    cluster_id = report["items"][0]["id"]
    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            target_id=uuid.UUID(str(case["id"])),
            action_type="heal_apply",
            payload={
                "failure_cluster_id": cluster_id,
                "cluster_confidence": 0.85,
                "fix_confidence": 0.85,
                "patch": {"assertions": [{"type": "status_code", "expected": 500}]},
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": case["version"],
            },
        ),
    )
    approval_id = preview.json()["data"]["approval_request_id"]
    from app.modules.test_assets import repository as assets_repo

    row = await assets_repo.get_test_case(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        test_case_id=uuid.UUID(str(case["id"])),
    )
    assert row is not None
    before_version_id = row.current_version_id
    row.aggregate_version += 1
    await db_session.commit()
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    approval = await client.get(f"/api/v1/approval-requests/{approval_id}")
    assert approval.json()["data"]["status"] == "EXECUTED"
    assert approval.json()["data"]["execution_result"] == "failed"
    row_after = await assets_repo.get_test_case(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        test_case_id=uuid.UUID(str(case["id"])),
    )
    assert row_after is not None
    assert row_after.current_version_id == before_version_id

    from app.modules.results_evidence.a2_service import (
        _validate_ai_clusters,
        rule_cluster_failed_cases,
    )

    case_id = uuid.uuid4()
    fallback = rule_cluster_failed_cases(
        [
            {
                "id": case_id,
                "normalized_summary": {"status_code": 500, "path": "/pets"},
                "step_assertions": [],
            }
        ]
    )
    assert fallback.degraded is True
    assert fallback.clusters[0].confidence == 0.3
    assert fallback.clusters[0].fixes == []
    rejected = _validate_ai_clusters(
        {
            "clusters": [
                {
                    "failure_refs": [str(case_id)],
                    "category": "assertion_real_bug",
                    "confidence": 0.9,
                    "evidence_refs": [str(uuid.uuid4())],
                    "blocking_judgment": "uncertain",
                }
            ],
            "unclustered_refs": [],
        },
        evidence_pool=set(),
        failed_case_ids={case_id},
    )
    assert rejected is None


@pytest.mark.asyncio
async def test_api_130_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from datetime import UTC, datetime

    from app.modules.identity_tenancy.models import (
        DEFAULT_CAPABILITY_CONTROLS,
        DEFAULT_SIEM_EXPORT,
        Organization,
        Project,
        User,
    )
    from app.modules.run_orchestration import repository as run_repo

    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    other_project = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other Org Clusters",
            slug="other-org-clusters",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            siem_export=dict(DEFAULT_SIEM_EXPORT),
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
            idp_subject="other-cluster-subject",
            display_name="Other",
            email="other-cluster@example.com",
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
            name="Secret Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    foreign = await run_repo.create_test_run(
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
        snapshot={
            "case_ids": [],
            "env_id": str(uuid.uuid4()),
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    await db_session.commit()
    await login_as(client)
    response = await client.get(f"/api/v1/test-runs/{foreign.id}/failure-clusters")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
