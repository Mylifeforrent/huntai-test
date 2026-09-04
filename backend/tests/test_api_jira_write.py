"""FR-14 jira_write tests (AC-063 / AC-064)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest
from app.modules.integration_hub import repository as connector_repo
from app.modules.integration_hub.jira_write_stub import JiraWriteSyncError
from app.modules.results_evidence.audit_models import AuditEvent
from app.modules.results_evidence.models import EvidenceObject
from tests.helpers import login_as
from tests.test_api_120_action_previews import _preview_body, _seed_admin_peer
from tests.test_api_130_131_039_heal import _start_failed_run


async def _seed_jira_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    outbound: bool = True,
    credential: str = "bound",
) -> uuid.UUID:
    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type="jira",
        name="Jira Org",
        credential_ref=credential,
        outbound_write_enabled=outbound,
    )
    await db_session.commit()
    return connector.id


async def _preview_jira_for_cluster(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    cluster: dict[str, object],
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            target_id=uuid.UUID(str(cluster["id"])),
            payload={
                "description": str(cluster.get("root_cause") or "failure"),
                "repro_steps": "repro",
                "jira_project": "HTST",
                "evidence_ids": cluster.get("evidence_refs") or [],
            },
        ),
    )
    assert response.status_code == 200
    return response.json()["data"]


async def _approve_as_peer(
    client: AsyncClient,
    *,
    approval_id: str,
    idp_subject: str = "admin-peer-120",
) -> None:
    await login_as(client, idp_subject=idp_subject)
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    assert detail.status_code == 200
    version = detail.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200


@pytest.mark.asyncio
async def test_ac_063_preview_without_approve_writes_nothing(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    result = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    for row in result.scalars().all():
        source = row.source_object if isinstance(row.source_object, dict) else {}
        assert source.get("connector") != "jira"


@pytest.mark.asyncio
async def test_ac_063_reject_decision_writes_nothing(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "reject", "expected_version": version},
    )
    result = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    for row in result.scalars().all():
        source = row.source_object if isinstance(row.source_object, dict) else {}
        assert source.get("connector") != "jira"


@pytest.mark.asyncio
async def test_ac_063_missing_connector_executed_failed_no_evidence(
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
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])
    await _approve_as_peer(client, approval_id=approval_id)
    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status == "EXECUTED"
    assert approval.execution_result == "failed"
    result = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    for row in result.scalars().all():
        source = row.source_object if isinstance(row.source_object, dict) else {}
        assert source.get("connector") != "jira"


@pytest.mark.asyncio
async def test_ac_064_approve_creates_issue_link_and_audit(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=None)
    run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])
    await _approve_as_peer(client, approval_id=approval_id)
    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status == "EXECUTED"
    assert approval.execution_result == "ok"
    evidence_rows = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    jira_rows = [
        row
        for row in evidence_rows.scalars().all()
        if isinstance(row.source_object, dict) and row.source_object.get("connector") == "jira"
    ]
    assert len(jira_rows) == 1
    source = jira_rows[0].source_object
    assert isinstance(source, dict)
    assert source.get("resource", "").startswith("HT-")
    await login_as(client)
    detail = await client.get(f"/api/v1/failure-clusters/{cluster['id']}")
    assert detail.status_code == 200
    jira_issue = detail.json()["data"].get("jira_issue")
    assert jira_issue is not None
    assert jira_issue["key"].startswith("HT-")
    assert jira_issue.get("external_request_id")
    run_after = await client.get(f"/api/v1/test-runs/{run['id']}")
    assert run_after.json()["data"]["status"] == "FAILED"
    audit_rows = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.action == "jira_write",
            AuditEvent.result == "ok",
        )
    )
    audit_row = audit_rows.scalars().first()
    assert audit_row is not None
    assert audit_row.external_request_id


@pytest.mark.asyncio
async def test_idempotent_same_approval_does_not_duplicate_issue(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])
    await _approve_as_peer(client, approval_id=approval_id)
    from app.modules.integration_hub import command_port as integration_command

    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.approver_id is not None
    second = await integration_command.execute_jira_write_after_approval(
        db_session,
        organization_id=org_id,
        approval_id=approval.id,
        bound_hash=approval.param_hash,
        actor_user_id=approval.approver_id,
        project_id=project_id,
        target_object_type=approval.target_object_type,
        target_object_id=approval.target_object_id,
        payload=approval.action_payload,
        request_hash="retry-hash",
    )
    assert second["status"] == "ok"
    assert second.get("duplicate") is True
    evidence_rows = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    jira_rows = [
        row
        for row in evidence_rows.scalars().all()
        if isinstance(row.source_object, dict) and row.source_object.get("connector") == "jira"
    ]
    assert len(jira_rows) == 1


@pytest.mark.asyncio
async def test_cross_tenant_cluster_preview_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client)
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            target_id=uuid.uuid4(),
            payload={
                "description": "x",
                "jira_project": "HTST",
            },
        ),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_jira_write_stub_retries_then_succeeds(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])
    calls = {"count": 0}

    async def flaky_apply(result: dict[str, object]) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] <= 2:
            raise JiraWriteSyncError("stub failure")
        return result

    with patch(
        "app.modules.integration_hub.jira_write_stub._apply_write",
        side_effect=flaky_apply,
    ):
        await _approve_as_peer(client, approval_id=approval_id)

    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.execution_result == "ok"
    assert calls["count"] == 3
