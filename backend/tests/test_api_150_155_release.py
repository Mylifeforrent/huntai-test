"""ReleaseTask tests (API-150…155, FR-15, S-M3-03)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.release_orchestration import service as release_service
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_admin_peer
from tests.test_api_jira_write import _seed_jira_connector


async def _poll_task_status(
    client: AsyncClient,
    task_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 100,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/release-tasks/{task_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.1)
    raise AssertionError(f"release task did not reach {wanted}")


async def _create_task(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    jira_version_ref: str = "v1.0",
) -> Any:
    await login_as(client)
    return await client.post(
        "/api/v1/release-tasks",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "jira_version_ref": jira_version_ref},
    )


async def _approve_as_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    approval_id: str,
) -> Any:
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await login_as(client, idp_subject="admin-peer-120")
    return await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )


async def _create_release_push_approval(
    client: AsyncClient,
    task_id: str,
    project_id: uuid.UUID,
) -> str:
    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "action_type": "release_push",
            "target_object_type": "release_task",
            "target_object_id": task_id,
            "project_id": str(project_id),
            "payload": {"confirm": True},
        },
    )
    assert preview.status_code == 200, preview.text
    approval_id = preview.json()["data"].get("approval_request_id")
    assert approval_id
    return str(approval_id)


@pytest.mark.asyncio
async def test_create_advance_and_readiness(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=user_id)
    create = await _create_task(client, project_id=project_id)
    assert create.status_code == 201, create.text
    task = create.json()["data"]
    task_id = str(task["id"])
    assert task["status"] == "DRAFT"
    assert task["scope_snapshot"]["jira_version_ref"] == "v1.0"

    # AC-066: A5 草稿就绪但不自动推送
    task_detail = await _poll_task_status(client, task_id, wanted={"PENDING_CONFIRM"})
    assert task_detail["a5"] is not None
    assert task_detail["notes_draft"]
    assert "jira_scope_issues" in task_detail["a5"]["missing_inputs"]

    readiness = await client.get(f"/api/v1/release-tasks/{task_id}/readiness")
    assert readiness.status_code == 200
    body = readiness.json()["data"]
    assert body["overall"] == "red"  # scope 为空 + 无门禁记录
    keys = {item["key"] for item in body["items"]}
    assert {"jira_scope", "gate_evaluation", "notes_draft"} <= keys

    # AC-065: 审计可追溯（创建 + 推进）
    audit = await client.get("/api/v1/audit-events", params={"project_id": str(project_id)})
    actions = [item.get("action") for item in audit.json()["data"]["items"]]
    assert "release_task.create" in actions
    assert "release_task.advance" in actions

    # 幂等重放
    replay = await client.post(
        "/api/v1/release-tasks",
        headers={"Idempotency-Key": "00000000-0000-4000-8000-0000000000f1"},
        json={"project_id": str(project_id), "jira_version_ref": "v1.0"},
    )
    first = await client.post(
        "/api/v1/release-tasks",
        headers={"Idempotency-Key": "00000000-0000-4000-8000-0000000000f1"},
        json={"project_id": str(project_id), "jira_version_ref": "v1.0"},
    )
    assert first.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]


@pytest.mark.asyncio
async def test_create_without_jira_connector_ext_error(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    response = await _create_task(client, project_id=project_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-EXT-001"


@pytest.mark.asyncio
async def test_release_push_approve_prepare_and_webhook_ready(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await _seed_jira_connector(db_session, org_id=org_id, user_id=user_id)
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    create = await _create_task(client, project_id=project_id)
    task_id = str(create.json()["data"]["id"])
    await _poll_task_status(client, task_id, wanted={"PENDING_CONFIRM"})

    approval_id = await _create_release_push_approval(client, task_id, project_id)
    decision = await _approve_as_admin(client, db_session, seeded_identity, approval_id)
    assert decision.status_code == 200, decision.text
    assert decision.json()["data"]["status"] == "EXECUTED"
    assert decision.json()["data"]["execution_result"] == "ok"

    task = await _poll_task_status(client, task_id, wanted={"SUBMITTED"})
    release_item = task["scope_snapshot"].get("release_item")
    assert release_item is not None
    external_item_id = release_item["external_item_id"]

    # webhook 观察 → READY（HMAC）
    detail = await client.get(f"/api/v1/release-tasks/{task_id}")
    version = detail.json()["data"]["version"]
    connector_id = await _seed_release_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps(
        {
            "release_task_id": task_id,
            "external_item_id": external_item_id,
            "status": "ready",
        }
    ).encode()
    secret = "test-github-webhook-secret"
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    webhook = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "x-hub-signature-256": signature,
            "x-github-delivery": str(uuid.uuid4()),
            "x-github-event": "release_item_ready",
            "content-type": "application/json",
        },
    )
    assert webhook.status_code == 202, webhook.text
    _ = version
    await _poll_task_status(client, task_id, wanted={"READY"})


async def _seed_release_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    from app.modules.integration_hub import repository as connector_repo

    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type="release",
        name="Release Org",
        credential_ref="bound",
        outbound_write_enabled=True,
        webhook_secret_ref="env:GITHUB_WEBHOOK_SECRET",
    )
    await db_session.commit()
    return connector.id


@pytest.mark.asyncio
async def test_retry_is_idempotent_and_never_duplicates_item(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await _seed_jira_connector(db_session, org_id=org_id, user_id=user_id)
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    create = await _create_task(client, project_id=project_id)
    task_id = str(create.json()["data"]["id"])
    await _poll_task_status(client, task_id, wanted={"PENDING_CONFIRM"})

    calls = {"count": 0}
    real_stub = release_service._release_connector_create_item

    async def failing_stub(**_kwargs: object) -> dict[str, object]:
        calls["count"] += 1
        raise RuntimeError("release system down")

    monkeypatch.setattr(release_service, "_release_connector_create_item", failing_stub)
    approval_id = await _create_release_push_approval(client, task_id, project_id)
    decision = await _approve_as_admin(client, db_session, seeded_identity, approval_id)
    assert decision.json()["data"]["execution_result"] == "failed"
    task = await _poll_task_status(client, task_id, wanted={"FAILED_RETRYABLE"})

    # 人工重试：stub 恢复 → item 创建一次
    async def ok_stub(**kwargs: object) -> dict[str, object]:
        calls["count"] += 1
        return await real_stub(**kwargs)

    monkeypatch.setattr(release_service, "_release_connector_create_item", ok_stub)
    detail = await client.get(f"/api/v1/release-tasks/{task_id}")
    version = detail.json()["data"]["version"]
    retry = await client.post(
        f"/api/v1/release-tasks/{task_id}/retries",
        headers={"Idempotency-Key": "00000000-0000-4000-8000-0000000000e1"},
        json={"expected_version": version},
    )
    assert retry.status_code == 202, retry.text
    item = None
    for _ in range(100):
        task_detail = await client.get(f"/api/v1/release-tasks/{task_id}")
        if task_detail.json()["data"]["scope_snapshot"].get("release_item") is not None:
            item = task_detail.json()["data"]["scope_snapshot"]["release_item"]
            break
        await asyncio.sleep(0.1)
    assert item is not None, f"item not prepared; status={task_detail.json()['data']['status']}"
    external_item_id = item["external_item_id"]

    # 再次 FAILED_RETRYABLE + 重试：幂等键命中，stub 不再调用，item 不重复
    from app.modules.release_orchestration.models import ReleaseItemRef, ReleaseTask

    await db_session.execute(
        ReleaseTask.__table__.update()
        .where(ReleaseTask.__table__.c.id == uuid.UUID(task_id))
        .values(status="FAILED_RETRYABLE")
    )
    await db_session.commit()
    detail = await client.get(f"/api/v1/release-tasks/{task_id}")
    version = detail.json()["data"]["version"]
    retry2 = await client.post(
        f"/api/v1/release-tasks/{task_id}/retries",
        headers={"Idempotency-Key": "00000000-0000-4000-8000-0000000000e2"},
        json={"expected_version": version},
    )
    assert retry2.status_code == 202, retry2.text
    for _ in range(100):
        task_detail = await client.get(f"/api/v1/release-tasks/{task_id}")
        if task_detail.json()["data"]["status"] == "SUBMITTED":
            break
        await asyncio.sleep(0.1)
    refs = (
        (
            await db_session.execute(
                select(ReleaseItemRef).where(ReleaseItemRef.release_task_id == uuid.UUID(task_id))
            )
        )
        .scalars()
        .all()
    )
    assert len(refs) == 1
    assert refs[0].external_item_id == external_item_id
    assert calls["count"] == 2  # 首次失败 + 首次成功；幂等命中不再调用
    _ = task


@pytest.mark.asyncio
async def test_cancel_and_late_ready_divergence(
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
    await _seed_jira_connector(db_session, org_id=org_id, user_id=user_id)
    create = await _create_task(client, project_id=project_id)
    task_id = str(create.json()["data"]["id"])
    await _poll_task_status(client, task_id, wanted={"PENDING_CONFIRM"})

    detail = await client.get(f"/api/v1/release-tasks/{task_id}")
    version = detail.json()["data"]["version"]
    cancel = await client.post(
        f"/api/v1/release-tasks/{task_id}/cancel",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["data"]["status"] == "CANCELLED"

    # CANCELLED 后迟到 READY 只追加 divergence
    from app.modules.release_orchestration import command_port as release_command

    result = await release_command.apply_release_observation(
        db_session,
        organization_id=org_id,
        body={"release_task_id": task_id, "external_item_id": "RI-LATE"},
        request_hash="late",
    )
    await db_session.commit()
    assert result == "divergence_appended"
    detail = await client.get(f"/api/v1/release-tasks/{task_id}")
    data = detail.json()["data"]
    assert data["status"] == "CANCELLED"
    assert data["divergence"]["late_ready"][0]["external_item_id"] == "RI-LATE"


@pytest.mark.asyncio
async def test_viewer_cannot_create_release_task(
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
    from app.modules.identity_tenancy.models import ProjectMember, User

    now = datetime.now(UTC)
    viewer_id = uuid.uuid4()
    db_session.add(
        User(
            id=viewer_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=viewer_id,
            aggregate_version=1,
            idp_subject="release-viewer",
            display_name="Viewer",
            email="release-viewer@example.com",
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
            created_by=viewer_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=viewer_id,
            role="viewer",
        )
    )
    await db_session.commit()
    await login_as(client, idp_subject="release-viewer")
    response = await client.post(
        "/api/v1/release-tasks",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"project_id": str(project_id), "jira_version_ref": "v1.0"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"
