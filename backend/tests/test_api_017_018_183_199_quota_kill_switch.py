"""API-017/018/183/199, quota exhaustion, kill switch tighten/restore tests."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.ai_governance.models import AIInvocationLog
from app.modules.approval_policy.models import ApprovalRequest
from app.modules.identity_tenancy.models import Organization
from app.modules.quota_governance.models import OrgQuota
from tests.ai_governance_helpers import seed_model_routes, seed_tester
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_admin_peer


async def _seed_other_org_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    now = datetime.now(UTC)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    from app.modules.identity_tenancy.models import (
        DEFAULT_CAPABILITY_CONTROLS,
        Organization,
        Project,
        ProjectMember,
        User,
    )

    db_session.add(
        Organization(
            id=org_id,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other Org",
            slug=f"other-{org_id.hex[:8]}",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject=f"other-{org_id.hex[:8]}",
            display_name="Other",
            email="other@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=project_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
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
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role="owner",
        )
    )
    await db_session.commit()
    return org_id, project_id


@pytest.mark.asyncio
async def test_api_017_owner_token_remaining(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.get("/api/v1/org-quotas/current")
    assert response.status_code == 200
    data = response.json()["data"]
    remaining = data["token_budget"] - data["token_reserved"] - data["token_consumed"]
    assert data["token_remaining"] == remaining


@pytest.mark.asyncio
async def test_api_017_tester_can_read(
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
    await seed_tester(db_session, org_id=org_id, project_id=project_id, idp_subject="tester-quota")
    await login_as(client, idp_subject="tester-quota")
    response = await client.get("/api/v1/org-quotas/current")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_018_member_and_cross_org_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    _, other_project_id = await _seed_other_org_project(db_session)
    await login_as(client)
    ok = await client.get(f"/api/v1/projects/{project_id}/quota-view")
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["project_id"] == str(project_id)
    assert "org_remaining" in body["view"]
    assert body["view"]["org_remaining"]["token_remaining"] is not None

    missing = await client.get(f"/api/v1/projects/{other_project_id}/quota-view")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_llm_factory_quota_exhausted_refused(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await db_session.execute(
        update(OrgQuota).where(OrgQuota.organization_id == org_id).values(token_budget=Decimal("0"))
    )
    await db_session.commit()

    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-quota",
            data_classification="Internal",
        ),
    )
    await db_session.commit()
    assert output.result == "refused"
    assert output.refusal_class == "quota"

    row = (
        await db_session.execute(select(AIInvocationLog).where(AIInvocationLog.id == output.log_id))
    ).scalar_one()
    assert row.result == "refused"


@pytest.mark.asyncio
async def test_api_183_cost_dashboard_and_errors(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-cost",
            data_classification="Internal",
        ),
    )
    await db_session.commit()

    await login_as(client)
    missing = await client.get("/api/v1/ai/cost-dashboard")
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "HT-VAL-001"

    now = datetime.now(UTC)
    response = await client.get(
        "/api/v1/ai/cost-dashboard",
        params={"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()},
    )
    assert response.status_code == 200
    totals = response.json()["data"]["totals"]
    assert totals["invocation_count"] >= 1
    assert "token_usage" in totals
    assert "adoption_rate" in totals

    await seed_tester(db_session, org_id=org_id, project_id=project_id, idp_subject="tester-cost")
    await login_as(client, idp_subject="tester-cost")
    forbidden = await client.get(
        "/api/v1/ai/cost-dashboard",
        params={"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_199_tighten_global_and_invoke_refused(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await login_as(client)

    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    version = org.aggregate_version
    key = str(uuid.uuid4())
    tighten = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": key},
        json={"expected_version": version, "target": {"level": "global"}, "reason": "incident"},
    )
    assert tighten.status_code == 200
    data = tighten.json()["data"]
    assert data["tightened"] is True

    me = await client.get("/api/v1/me")
    controls = me.json()["data"]["organization"]["capability_controls"]
    assert controls["ai_global_tightened"] is True

    db_session.expire_all()
    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-kill",
            data_classification="Internal",
        ),
    )
    await db_session.commit()
    assert output.result == "refused"
    assert output.refusal_class == "kill_switch"


@pytest.mark.asyncio
async def test_api_199_restore_fields_rejected(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    await login_as(client)
    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    before = dict(org.capability_controls)

    for body in (
        {
            "expected_version": org.aggregate_version,
            "target": {"level": "global"},
            "direction": "restore",
        },
        {
            "expected_version": org.aggregate_version,
            "target": {"level": "global"},
            "enabled": True,
        },
        {
            "expected_version": org.aggregate_version,
            "target": {"level": "global"},
            "loosen": True,
        },
    ):
        response = await client.post(
            "/api/v1/organizations/current/capability-controls/tighten",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=body,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "HT-VAL-001"

    await db_session.refresh(org)
    assert org.capability_controls == before


@pytest.mark.asyncio
async def test_api_199_tester_forbidden(
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
    await seed_tester(db_session, org_id=org_id, project_id=project_id, idp_subject="tester-199")
    await login_as(client, idp_subject="tester-199")
    response = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": 1, "target": {"level": "global"}},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_199_idempotent_replay(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    await login_as(client)
    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    key = str(uuid.uuid4())
    body = {
        "expected_version": org.aggregate_version,
        "target": {"level": "module", "module": "perf"},
    }
    first = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200
    second = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert second.status_code == 200
    assert second.json()["data"]["tightened"] is True


@pytest.mark.asyncio
async def test_api_199_version_conflict(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": 999, "target": {"level": "global"}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_kill_switch_restore_approve_executes(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)
    await login_as(client)

    org = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    tighten = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": org.aggregate_version, "target": {"level": "global"}},
    )
    assert tighten.status_code == 200
    org_version = tighten.json()["data"]["version"]

    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "action_type": "kill_switch_restore",
            "target_object_type": "organization",
            "target_object_id": str(org_id),
            "payload": {"target": {"level": "global", "id": "global"}},
            "expected_target_version": org_version,
        },
    )
    assert preview.status_code == 200
    approval_id = preview.json()["data"]["approval_request_id"]

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
    assert data["execution_result"] == "ok"

    await db_session.refresh(org)
    assert org.capability_controls.get("ai_global_tightened") is False

    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-restored",
            data_classification="Internal",
        ),
    )
    await db_session.commit()
    assert output.result == "degraded"


@pytest.mark.asyncio
async def test_non_restore_approve_stays_approved(
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
    preview = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "action_type": "agent_tool_action",
            "project_id": str(project_id),
            "target_object_type": "test_run",
            "target_object_id": str(uuid.uuid4()),
            "payload": {
                "declared_side_effect_level": "L2",
                "tool_name": "noop",
            },
        },
    )
    assert preview.status_code == 200
    approval_id = preview.json()["data"]["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["status"] == "APPROVED"
    assert decision.json()["data"].get("execution_result") is None

    row = (
        await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == uuid.UUID(str(approval_id)))
        )
    ).scalar_one()
    assert row.status == "APPROVED"
    assert row.execution_result is None
