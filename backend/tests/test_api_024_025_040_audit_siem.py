"""API-024/025 audit search and API-040 SIEM export config."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_models import AuditEvent
from tests.ai_governance_helpers import seed_model_routes, seed_tester
from tests.helpers import login_as
from tests.test_api_120_action_previews import _preview_body, _seed_admin_peer


async def _tighten_global(client: AsyncClient, *, expected_version: int) -> None:
    response = await client.post(
        "/api/v1/organizations/current/capability-controls/tighten",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": expected_version,
            "target": {"level": "global"},
            "reason": "audit test tighten",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_024_owner_lists_audited_write_without_prompt(
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

    await login_as(client)
    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    await _tighten_global(client, expected_version=version)

    response = await client.get("/api/v1/audit-events")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    match = next(item for item in items if item.get("action") == "organization.capability_tighten")
    assert match["actor_user_id"] == str(user_id)
    assert "prompt" not in match


@pytest.mark.asyncio
async def test_api_024_tester_forbidden(
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
    await seed_tester(db_session, org_id=org_id, project_id=project_id, idp_subject="tester-audit")
    await login_as(client, idp_subject="tester-audit")

    response = await client.get("/api/v1/audit-events")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_025_get_detail_and_cross_tenant_not_found(
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

    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    await _tighten_global(client, expected_version=version)

    list_resp = await client.get("/api/v1/audit-events")
    event_id = list_resp.json()["data"]["items"][0]["id"]

    detail = await client.get(f"/api/v1/audit-events/{event_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == event_id
    assert "prompt" not in detail.json()["data"]

    missing = await client.get(f"/api/v1/audit-events/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_024_includes_failed_command_audit(
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

    failed = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(
            project_id=project_id,
            action_type="agent_tool_action",
            payload={},
        ),
    )
    assert failed.status_code == 403

    response = await client.get("/api/v1/audit-events", params={"resource_type": "action_preview"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(item.get("result") == "failed" for item in items)


@pytest.mark.asyncio
async def test_api_040_disable_siem_idempotent_and_projection(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange
    await login_as(client)

    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    body = {"expected_version": version, "enabled": False}
    idem_key = str(uuid.uuid4())
    put_resp = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert put_resp.status_code == 200
    data = put_resp.json()["data"]
    assert data["enabled"] is False
    assert data["version"] == version + 1
    assert data["credential_present"] is False

    me_resp = await client.get("/api/v1/me")
    assert me_resp.json()["data"]["organization"]["siem_export_enabled"] is False
    org_after = await client.get("/api/v1/organizations/current")
    assert org_after.json()["data"]["siem_export_enabled"] is False

    replay = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["version"] == version + 1


@pytest.mark.asyncio
async def test_api_040_enable_without_connector_validation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange
    await login_as(client)
    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    response = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "enabled": True},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_040_enable_with_connector_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange
    await login_as(client)
    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    response = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "enabled": True,
            "destination_connector_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_040_admin_forbidden(
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
    await _seed_admin_peer(
        db_session, org_id=org_id, project_id=project_id, idp_subject="admin-siem"
    )
    await login_as(client, idp_subject="admin-siem")
    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    response = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version, "enabled": False},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_040_version_conflict(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange
    await login_as(client)
    org_resp = await client.get("/api/v1/organizations/current")
    version = org_resp.json()["data"]["version"]
    response = await client.put(
        "/api/v1/organizations/current/siem-export",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version + 99, "enabled": False},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_api_024_filter_actor_user_id(
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
    await _seed_admin_peer(
        db_session, org_id=org_id, project_id=project_id, idp_subject="admin-audit-filter"
    )
    await login_as(client)

    org_resp = await client.get("/api/v1/organizations/current")
    await _tighten_global(client, expected_version=org_resp.json()["data"]["version"])

    filtered = await client.get(
        "/api/v1/audit-events",
        params={"actor_user_id": str(user_id)},
    )
    assert filtered.status_code == 200
    items = filtered.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item["actor_user_id"] == str(user_id) for item in items)

    other = await client.get(
        "/api/v1/audit-events",
        params={"actor_user_id": str(uuid.uuid4())},
    )
    assert other.status_code == 200
    assert other.json()["data"]["items"] == []

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.action == "organization.capability_tighten",
        )
    )
    assert result.scalars().first() is not None
