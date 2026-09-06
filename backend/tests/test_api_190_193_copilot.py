"""Copilot minimal tests (API-190…193, FR-16, S-M3-04)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.models import AIInvocationLog
from tests.helpers import login_as


async def _seed_run(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    project_id: uuid.UUID,
) -> uuid.UUID:
    from app.modules.run_orchestration.models import TestRun

    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
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
    return run.id


async def _create_session(
    client: AsyncClient,
    *,
    project_id: uuid.UUID | None = None,
) -> dict[str, object]:
    await login_as(client)
    body: dict[str, object] = {"title": "qa session"}
    if project_id is not None:
        body["project_id"] = str(project_id)
    response = await client.post("/api/v1/copilot-sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.mark.asyncio
async def test_session_crud_and_ownership_isolation(
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
    session_a = await _create_session(client, project_id=project_id)
    session_id = str(session_a["id"])

    listing = await client.get("/api/v1/copilot-sessions")
    items = listing.json()["data"]["items"]
    assert any(item["id"] == session_id for item in items)

    # 其他同组织用户不可见、不可问（归属隔离）
    from datetime import datetime

    from app.modules.identity_tenancy.models import ProjectMember, User

    now = datetime.now(UTC)
    other_id = uuid.uuid4()
    db_session.add(
        User(
            id=other_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=other_id,
            aggregate_version=1,
            idp_subject="copilot-peer",
            display_name="Peer",
            email="copilot-peer@example.com",
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
            created_by=other_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=other_id,
            role="tester",
        )
    )
    await db_session.commit()
    await login_as(client, idp_subject="copilot-peer")
    others_listing = await client.get("/api/v1/copilot-sessions")
    assert not [item for item in others_listing.json()["data"]["items"] if item["id"] == session_id]
    cross = await client.get(f"/api/v1/copilot-sessions/{session_id}")
    assert cross.status_code == 404
    message = await client.post(
        f"/api/v1/copilot-sessions/{session_id}/messages",
        json={"content": "最新 run 怎么样？"},
    )
    assert message.status_code == 404


@pytest.mark.asyncio
async def test_viewer_create_fail_close_and_skill_rejected(
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
    from datetime import datetime

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
            idp_subject="copilot-viewer",
            display_name="Viewer",
            email="copilot-viewer@example.com",
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
    await login_as(client, idp_subject="copilot-viewer")
    response = await client.post("/api/v1/copilot-sessions", json={"title": "v"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"

    await login_as(client)
    skill = await client.post(
        "/api/v1/copilot-sessions",
        json={"selected_skill_version_id": str(uuid.uuid4())},
    )
    # Skill 域是 M4：fail-close 不接受技能指针
    assert skill.status_code == 404
    assert skill.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_kill_switch_blocks_messages(
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
    session = await _create_session(client, project_id=project_id)
    session_id = str(session["id"])

    from sqlalchemy import select

    from app.modules.identity_tenancy.models import Organization

    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    tighten = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": org.aggregate_version,
            "target": {"level": "module", "module": "copilot"},
            "reason": "kill switch drill",
        },
    )
    assert tighten.status_code == 200, tighten.text

    message = await client.post(
        f"/api/v1/copilot-sessions/{session_id}/messages",
        json={"content": "最新 run 怎么样？"},
    )
    assert message.status_code == 403
    assert message.json()["error"]["code"] == "HT-POL-001"


@pytest.mark.asyncio
async def test_quota_exhaustion_returns_429(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    from sqlalchemy import update

    from app.modules.quota_governance.models import OrgQuota

    session = await _create_session(client, project_id=project_id)
    session_id = str(session["id"])
    await db_session.execute(update(OrgQuota).values(token_consumed=OrgQuota.token_budget))
    await db_session.commit()
    message = await client.post(
        f"/api/v1/copilot-sessions/{session_id}/messages",
        json={"content": "最新 run 怎么样？"},
    )
    assert message.status_code == 429
    assert message.json()["error"]["code"] == "HT-QUOTA-001"


@pytest.mark.asyncio
async def test_cross_project_reference_is_refused(
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
    # 项目 B 的 run（同组织、用户非成员）
    other_project = uuid.uuid4()
    foreign_run = await _seed_run(db_session, seeded_identity, project_id=other_project)
    own_run = await _seed_run(db_session, seeded_identity, project_id=project_id)

    session = await _create_session(client, project_id=project_id)
    session_id = str(session["id"])
    message = await client.post(
        f"/api/v1/copilot-sessions/{session_id}/messages",
        json={"content": f"看看这个 run {foreign_run} 的结果，再对比 {own_run}"},
    )
    assert message.status_code == 200, message.text
    data = message.json()["data"]
    # AC-068: 四键恒在；越权引用 100% 拒绝
    assert {"answer", "citations", "tool_calls", "refused_policies"} <= set(data.keys())
    assert any(entry.startswith("cross_project_reference") for entry in data["refused_policies"])
    cited_ids = {item["resource_id"] for item in data["citations"]}
    assert str(foreign_run) not in cited_ids
    assert str(own_run) in cited_ids
    assert foreign_run.__str__() not in data["answer"] or "已拒绝" in data["answer"]

    # AIInvocationLog 全量记录（copilot_session_id 关联）
    logs = (
        (
            await db_session.execute(
                select(AIInvocationLog).where(
                    AIInvocationLog.copilot_session_id == uuid.UUID(session_id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert logs
