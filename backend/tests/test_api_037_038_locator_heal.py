"""API-037/038 and locator heal AC-048–050 tests (S-M2-02)."""

from __future__ import annotations

import asyncio
import json
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
from tests.test_api_120_action_previews import _preview_body
from tests.test_api_220_221_artifacts import create_active_web_case
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case


def _enable_playwright_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLAYWRIGHT_WORKER_STUB", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()


async def _start_web_run(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    env: dict[str, object],
    case_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    _enable_playwright_stub(monkeypatch)
    await login_as(client)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            **_start_body(
                project_id=project_id,
                env_id=env["id"],
                case_ids=[case_id],
                expected_env_version=env["version"],
            ),
            "params": {"TARGET_ENV": "https://example.test"},
        },
    )
    assert start.status_code == 200, start.text
    return str(start.json()["data"]["id"])


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 80,
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
    max_attempts: int = 80,
) -> dict[str, Any]:
    for _ in range(max_attempts):
        response = await client.get(f"/api/v1/test-runs/{run_id}/failure-clusters")
        assert response.status_code == 200
        payload = response.json()["data"]
        if payload.get("generation_status") in wanted_status:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError(f"cluster report did not reach {wanted_status}")


def _ok_a2_invoke(clusters_payload: dict[str, Any]):
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


def _ok_a3_invoke(a3_payload: dict[str, Any]):
    async def _mock_invoke(session: object, request: object) -> InvokeOutput:
        _ = session
        _ = request
        return InvokeOutput(
            log_id=uuid.uuid4(),
            result="ok",
            model="test-model",
            usage={"structured_output": a3_payload},
            cost=Decimal("0"),
            latency_ms=1,
            data_classification="Confidential",
        )

    return _mock_invoke


@pytest.mark.asyncio
async def test_api_037_lists_versions_without_snapshot(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    await login_as(client)
    response = await client.get(f"/api/v1/test-cases/{case['id']}/versions")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert items[0]["is_current"] is True
    assert "snapshot" not in items[0]
    assert items[0]["version_seq"] == 1


@pytest.mark.asyncio
async def test_api_038_snapshot_includes_locator_health(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    version_id = case["current_version_id"]
    await login_as(client)
    response = await client.get(f"/api/v1/test-cases/{case['id']}/versions/{version_id}")
    assert response.status_code == 200
    snapshot = response.json()["data"]["snapshot"]
    locators = snapshot.get("locator_health", [])
    assert locators
    assert locators[0]["expression"] == "#missing"
    assert locators[0]["health"] == "unknown"
    assert locators[0]["is_primary"] is True


def test_extract_locator_health_first_primary_only() -> None:
    from app.modules.test_assets.locator_health import extract_locator_health_from_steps

    locators = extract_locator_health_from_steps(
        [
            {"action": "click", "params": {"selector": "#one"}},
            {"action": "fill", "params": {"selector": "#two"}},
        ]
    )
    assert [item["is_primary"] for item in locators] == [True, False]


def test_a3_accepts_locator_containing_click_word() -> None:
    from app.modules.results_evidence.a3_service import _validate_candidates

    out = _validate_candidates(
        [{"expression": "text=Click Submit", "strategy": "text", "confidence": 0.9}]
    )
    assert len(out) == 1
    assert out[0]["expression"] == "text=Click Submit"


@pytest.mark.asyncio
async def test_api_038_wrong_case_or_tenant_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    other_case_id = uuid.uuid4()
    await login_as(client)
    wrong_case = await client.get(
        f"/api/v1/test-cases/{other_case_id}/versions/{case['current_version_id']}"
    )
    assert wrong_case.status_code == 404
    versions = await client.get(f"/api/v1/test-cases/{other_case_id}/versions")
    assert versions.status_code == 404


@pytest.mark.asyncio
async def test_api_037_unauthenticated_401(
    client: AsyncClient,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    client.cookies.clear()
    response = await client.get(
        f"/api/v1/test-cases/{uuid.uuid4()}/versions",
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ac_048_active_locator_health_not_auto_rewritten(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    await login_as(client)
    version_id = case["current_version_id"]
    before_snapshot = (
        await client.get(f"/api/v1/test-cases/{case['id']}/versions/{version_id}")
    ).json()["data"]["snapshot"]
    before_locators = before_snapshot.get("locator_health", [])
    patch_resp = await client.patch(
        f"/api/v1/test-cases/{case['id']}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": case["version"]},
    )
    assert patch_resp.status_code == 409
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    run_id = await _start_web_run(
        client,
        project_id=project_id,
        env=env,
        case_id=str(case["id"]),
        monkeypatch=monkeypatch,
    )
    await _poll_run_status(client, run_id, wanted={"FAILED", "SUCCEEDED"})
    from app.modules.test_assets import repository as assets_repo

    row = await assets_repo.get_test_case(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        test_case_id=uuid.UUID(str(case["id"])),
    )
    assert row is not None
    version = await assets_repo.get_test_case_version(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        version_id=row.current_version_id,  # type: ignore[arg-type]
    )
    assert version is not None
    assert version.snapshot.get("locator_health", []) == before_locators


@pytest.mark.asyncio
async def test_ac_049_locator_heal_apply_creates_new_version(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    run_id = await _start_web_run(
        client,
        project_id=project_id,
        env=env,
        case_id=str(case["id"]),
        monkeypatch=monkeypatch,
    )
    await _poll_run_status(client, run_id, wanted={"FAILED"})
    case_results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    case_result_id = case_results.json()["data"]["items"][0]["id"]
    clusters_payload = {
        "clusters": [
            {
                "failure_refs": [case_result_id],
                "category": "locator_stale",
                "confidence": 0.85,
                "evidence_refs": [],
                "blocking_judgment": "blocker",
                "fixes": [],
            }
        ],
        "unclustered_refs": [],
    }
    new_expression = "#healed-button"
    a3_payload = {
        "case_id": str(case["id"]),
        "locator_id": "loc-test",
        "candidates": [
            {
                "strategy": "css",
                "expression": new_expression,
                "reason": "updated selector",
                "confidence": 0.9,
            }
        ],
        "semantic_invariant_note": "same button",
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
            FailureCluster.test_run_id == uuid.UUID(str(run_id)),
        )
    )
    await run_command.merge_clustering_projection(
        db_session,
        organization_id=org_id,
        test_run_id=uuid.UUID(str(run_id)),
        clustering={"generation_status": "pending", "degraded": False, "unclustered_refs": []},
    )
    await db_session.commit()
    a2_patch = patch(
        "app.modules.results_evidence.a2_service.invoke",
        new=_ok_a2_invoke(clusters_payload),
    )
    a3_patch = patch(
        "app.modules.results_evidence.a3_service.invoke",
        new=_ok_a3_invoke(a3_payload),
    )
    with a2_patch, a3_patch:
        await run_failure_triage_background(
            organization_id=org_id,
            test_run_id=uuid.UUID(str(run_id)),
        )
    await login_as(client)
    report = await _poll_cluster_report(client, run_id, wanted_status={"ready", "degraded"})
    cluster_id = report["items"][0]["id"]
    detail = await client.get(f"/api/v1/failure-clusters/{cluster_id}")
    fix = detail.json()["data"]["fixes_preview"][0]
    assert fix["field"] == "locator_health"
    assert fix["confidence"] >= 0.7
    patch_body = json.loads(fix["suggested"])
    case_detail = await client.get(f"/api/v1/test-cases/{case['id']}")
    case_row = case_detail.json()["data"]
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
                "fix_confidence": fix["confidence"],
                "patch": patch_body,
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": case_row["version"],
            },
        ),
    )
    assert preview.status_code == 200
    approval_id = preview.json()["data"]["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    approval_detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": approval_detail.json()["data"]["version"]},
    )
    await login_as(client)
    healed = await client.get(f"/api/v1/test-cases/{case['id']}")
    assert healed.json()["data"]["version"] > case_row["version"]
    locators = healed.json()["data"]["locator_health"]
    primary = next(item for item in locators if item.get("is_primary"))
    assert primary["expression"] == new_expression


@pytest.mark.asyncio
async def test_ac_050_rollback_then_start_run_accepted(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    original_version_id = case["current_version_id"]
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    run_id = await _start_web_run(
        client,
        project_id=project_id,
        env=env,
        case_id=str(case["id"]),
        monkeypatch=monkeypatch,
    )
    await _poll_run_status(client, run_id, wanted={"FAILED"})
    case_results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    case_result_id = case_results.json()["data"]["items"][0]["id"]
    clusters_payload = {
        "clusters": [
            {
                "failure_refs": [case_result_id],
                "category": "locator_stale",
                "confidence": 0.85,
                "evidence_refs": [],
                "blocking_judgment": "blocker",
                "fixes": [],
            }
        ],
        "unclustered_refs": [],
    }
    a3_payload = {
        "candidates": [
            {
                "strategy": "css",
                "expression": "#rollback-target",
                "reason": "heal",
                "confidence": 0.9,
            }
        ],
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
            FailureCluster.test_run_id == uuid.UUID(str(run_id)),
        )
    )
    await run_command.merge_clustering_projection(
        db_session,
        organization_id=org_id,
        test_run_id=uuid.UUID(str(run_id)),
        clustering={"generation_status": "pending", "degraded": False, "unclustered_refs": []},
    )
    await db_session.commit()
    a2_patch = patch(
        "app.modules.results_evidence.a2_service.invoke",
        new=_ok_a2_invoke(clusters_payload),
    )
    a3_patch = patch(
        "app.modules.results_evidence.a3_service.invoke",
        new=_ok_a3_invoke(a3_payload),
    )
    with a2_patch, a3_patch:
        await run_failure_triage_background(
            organization_id=org_id,
            test_run_id=uuid.UUID(str(run_id)),
        )
    await login_as(client)
    report = await client.get(f"/api/v1/test-runs/{run_id}/failure-clusters")
    cluster_id = report.json()["data"]["items"][0]["id"]
    fix = (await client.get(f"/api/v1/failure-clusters/{cluster_id}")).json()["data"][
        "fixes_preview"
    ][0]
    patch_body = json.loads(fix["suggested"])
    case_detail = await client.get(f"/api/v1/test-cases/{case['id']}")
    case_row = case_detail.json()["data"]
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
                "fix_confidence": fix["confidence"],
                "patch": patch_body,
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": case_row["version"],
            },
        ),
    )
    approval_id = preview.json()["data"]["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    approval_detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": approval_detail.json()["data"]["version"]},
    )
    await login_as(client)
    healed = await client.get(f"/api/v1/test-cases/{case['id']}")
    healed_row = healed.json()["data"]
    rollback = await client.post(
        f"/api/v1/test-cases/{case['id']}/rollback",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": healed_row["version"],
            "target_version_id": original_version_id,
            "reason": "rollback heal",
        },
    )
    assert rollback.status_code == 200
    restart = await client.post(
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
    assert restart.status_code == 200


@pytest.mark.asyncio
async def test_a3_degraded_overlay_hint_no_high_confidence_fix(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    case = await create_active_web_case(client, project_id=project_id)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    run_id = await _start_web_run(
        client,
        project_id=project_id,
        env=env,
        case_id=str(case["id"]),
        monkeypatch=monkeypatch,
    )
    await _poll_run_status(client, run_id, wanted={"FAILED"})
    case_results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    case_result_id = case_results.json()["data"]["items"][0]["id"]
    clusters_payload = {
        "clusters": [
            {
                "failure_refs": [case_result_id],
                "category": "locator_stale",
                "confidence": 0.85,
                "evidence_refs": [],
                "blocking_judgment": "blocker",
                "fixes": [],
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
            FailureCluster.test_run_id == uuid.UUID(str(run_id)),
        )
    )
    await run_command.merge_clustering_projection(
        db_session,
        organization_id=org_id,
        test_run_id=uuid.UUID(str(run_id)),
        clustering={"generation_status": "pending", "degraded": False, "unclustered_refs": []},
    )
    await db_session.commit()
    a2_only = patch(
        "app.modules.results_evidence.a2_service.invoke",
        new=_ok_a2_invoke(clusters_payload),
    )
    with a2_only:
        await run_failure_triage_background(
            organization_id=org_id,
            test_run_id=uuid.UUID(str(run_id)),
        )
    await login_as(client)
    detail = await client.get(f"/api/v1/test-cases/{case['id']}")
    locators = detail.json()["data"]["locator_health"]
    assert locators
    assert any(
        isinstance(item.get("human_repair_hint"), str) and item["human_repair_hint"]
        for item in locators
    )
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
                "patch": {"locator_health": []},
            },
            extra={
                "target_object_type": "test_case",
                "expected_target_version": detail.json()["data"]["version"],
            },
        ),
    )
    assert preview.status_code == 403


@pytest.mark.asyncio
async def test_rule_fallback_web_click_still_env_down_for_api_500(
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
    case = await create_active_script_case(
        client,
        project_id=project_id,
        assertions=[{"type": "status_code", "expected": 200}],
    )
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = 500
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
    run_id = start.json()["data"]["id"]
    report = await _poll_cluster_report(client, run_id, wanted_status={"degraded"})
    assert report["items"][0]["category"] == "env_down"
