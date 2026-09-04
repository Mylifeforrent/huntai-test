"""API-110/111/112/113/121 approval queue tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)
from tests.helpers import login_as
from tests.test_api_120_action_previews import (
    _jira_preview_payload,
    _preview_body,
    _seed_admin_peer,
    _seed_jira_preview_target,
    _seed_viewer,
)


async def _create_pending_approval(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    project_id: uuid.UUID,
    idempotency_suffix: str = "default",
) -> dict[str, object]:
    cluster_id, cluster = await _seed_jira_preview_target(client, db_session, seeded_identity)
    key = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=_preview_body(
            project_id=project_id,
            target_id=cluster_id,
            payload=_jira_preview_payload(cluster),
        ),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return data


def _nine_card_keys(card_payload: dict[str, object]) -> None:
    for key in (
        "action",
        "resource",
        "diff",
        "data_source",
        "model_and_skill_version",
        "risk_level",
        "cost_estimate",
        "rollback",
        "param_hash",
    ):
        assert key in card_payload


@pytest.mark.asyncio
async def test_api_110_111_after_preview_pending_with_nine_card_keys(
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
    await login_as(client)

    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]
    assert approval_id

    list_resp = await client.get("/api/v1/approval-requests", params={"perspective": "all"})
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    item = next(row for row in items if row["id"] == approval_id)
    assert item["status"] == "PENDING"
    assert item["param_hash"]
    assert item["version"] >= 1
    _nine_card_keys(item["card_payload"])

    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["status"] == "PENDING"
    _nine_card_keys(body["card_payload"])
    assert "action_payload_redacted" in body


@pytest.mark.asyncio
async def test_api_112_peer_admin_approve_without_connector_executed_failed(
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
    peer_id = await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]

    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200
    data = decision.json()["data"]
    assert data["status"] == "EXECUTED"
    assert data.get("execution_result") == "failed"

    result = await db_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == uuid.UUID(str(approval_id)))
    )
    row = result.scalar_one()
    assert row.status == "EXECUTED"
    assert row.execution_result == "failed"
    assert row.approver_id == peer_id


@pytest.mark.asyncio
async def test_api_112_initiator_approve_four_eyes(
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
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]

    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 403
    assert decision.json()["error"]["code"] == "HT-IAM-002"

    result = await db_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == uuid.UUID(str(approval_id)))
    )
    assert result.scalar_one().status == "PENDING"


@pytest.mark.asyncio
async def test_api_112_peer_reject_with_reason(
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
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]

    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "reject", "reason": "not needed", "expected_version": version},
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_api_112_viewer_cannot_decide(
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
    await _seed_viewer(db_session, org_id=org_id, project_id=project_id)
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

    await login_as(client, idp_subject="viewer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 403
    assert decision.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_111_cross_org_not_found(
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
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

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
            name="Other Org",
            slug="other-org",
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
            idp_subject="other-org-user",
            display_name="Other",
            email="other@example.com",
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
            name="Other Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            user_id=other_user,
            role="owner",
        )
    )
    await db_session.commit()

    await login_as(client, idp_subject="other-org-user")
    response = await client.get(f"/api/v1/approval-requests/{approval_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_113_resubmit_from_rejected_creates_new_pending(
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
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]
    old_hash = preview["param_hash"]

    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "reject", "reason": "retry", "expected_version": version},
    )

    await login_as(client)
    resubmit = await client.post(
        f"/api/v1/approval-requests/{approval_id}/resubmissions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"payload": {"summary": "updated"}},
    )
    assert resubmit.status_code == 200
    body = resubmit.json()["data"]
    assert body["origin_request_id"] == approval_id
    assert body["origin_final_status"] == "REJECTED"
    new_item = body["new_approval_request"]
    assert new_item["status"] == "PENDING"
    assert new_item["param_hash"] != old_hash
    assert new_item["origin_request_id"] == approval_id

    origin = await db_session.get(ApprovalRequest, uuid.UUID(str(approval_id)))
    assert origin is not None
    assert origin.status == "REJECTED"


@pytest.mark.asyncio
async def test_api_113_resubmit_from_pending_withdraws_origin(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

    resubmit = await client.post(
        f"/api/v1/approval-requests/{approval_id}/resubmissions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"payload": {"summary": "changed"}},
    )
    assert resubmit.status_code == 200
    body = resubmit.json()["data"]
    assert body["origin_final_status"] == "EXPIRED"

    origin = await db_session.get(ApprovalRequest, uuid.UUID(str(approval_id)))
    assert origin is not None
    assert origin.status == "EXPIRED"
    assert origin.expired_reason == "withdrawn"


@pytest.mark.asyncio
async def test_api_121_get_preview_and_unknown_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    preview_id = preview["preview_id"]

    get_resp = await client.get(f"/api/v1/action-previews/{preview_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["preview_id"] == preview_id

    unknown = await client.get(f"/api/v1/action-previews/{uuid.uuid4()}")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_110_lazy_expire_pending(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = uuid.UUID(str(preview["approval_request_id"]))
    past = datetime.now(UTC) - timedelta(seconds=10)
    await db_session.execute(
        update(ApprovalRequest).where(ApprovalRequest.id == approval_id).values(expires_at=past)
    )
    await db_session.commit()

    list_resp = await client.get(
        "/api/v1/approval-requests",
        params={"status": "EXPIRED", "perspective": "all"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert any(item["id"] == str(approval_id) for item in items)
    expired = next(item for item in items if item["id"] == str(approval_id))
    assert expired["expired_reason"] == "ttl"

    await login_as(client, idp_subject="admin-peer-120")
    inbox = await client.get("/api/v1/approval-requests", params={"perspective": "inbox"})
    assert inbox.status_code == 200
    assert all(item["id"] != str(approval_id) for item in inbox.json()["data"]["items"])


@pytest.mark.asyncio
async def test_api_112_param_hash_mismatch_invalidates(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = uuid.UUID(str(preview["approval_request_id"]))

    await db_session.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id)
        .values(action_payload={"summary": "tampered"})
    )
    await db_session.commit()

    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 409
    assert decision.json()["error"]["code"] == "HT-APPR-001"

    origin = await db_session.get(ApprovalRequest, approval_id)
    assert origin is not None
    assert origin.status == "EXPIRED"
    assert origin.expired_reason == "invalidated"


@pytest.mark.asyncio
async def test_api_112_expected_version_mismatch(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    preview = await _create_pending_approval(
        client, db_session, seeded_identity, project_id=project_id
    )
    approval_id = preview["approval_request_id"]

    await login_as(client, idp_subject="admin-peer-120")
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        json={"decision": "approve", "expected_version": 999},
    )
    assert decision.status_code == 409
    assert decision.json()["error"]["code"] == "HT-VER-001"
