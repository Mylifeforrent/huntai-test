import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest
from app.modules.identity_tenancy.models import (
    AuthSession,
    ProjectMember,
    User,
)
from tests.helpers import login_as


def _preview_body(
    *,
    project_id: uuid.UUID,
    target_id: uuid.UUID | None = None,
    action_type: str = "jira_write",
    payload: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "action_type": action_type,
        "project_id": str(project_id),
        "target_object_type": "failure_cluster",
        "target_object_id": str(target_id or uuid.uuid4()),
        "payload": payload or {"summary": "test"},
    }
    if extra:
        body.update(extra)
    return body


async def _seed_admin_peer(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "admin-peer-120",
) -> uuid.UUID:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject=idp_subject,
            display_name="Admin Peer",
            email=f"{idp_subject}@example.com",
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
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role="admin",
        )
    )
    await db_session.commit()
    return user_id


async def _seed_viewer(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "viewer-120",
) -> uuid.UUID:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject=idp_subject,
            display_name="Viewer",
            email=f"{idp_subject}@example.com",
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
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role="viewer",
        )
    )
    await db_session.commit()
    return user_id


async def _stale_session(db_session: AsyncSession, client: AsyncClient) -> None:
    cookie = client.cookies.get("huntai_session")
    assert cookie is not None
    session_id = uuid.UUID(cookie)
    stale_at = datetime.now(UTC) - timedelta(seconds=2000)
    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(last_reauth_at=stale_at, created_at=stale_at)
    )
    await db_session.commit()


async def _fresh_reauth(db_session: AsyncSession, client: AsyncClient) -> None:
    cookie = client.cookies.get("huntai_session")
    assert cookie is not None
    session_id = uuid.UUID(cookie)
    await db_session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(last_reauth_at=datetime.now(UTC))
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_api_120_happy_l2_jira_write(
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
    key = str(uuid.uuid4())
    body = _preview_body(project_id=project_id)
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["gate"] == "REQUIRE_APPROVAL"
    assert data["action_type"] == "jira_write"
    assert data["param_hash"]
    assert data["approval_request_id"]
    assert data["card_payload"]["param_hash"] == data["param_hash"]

    result = await db_session.execute(select(ApprovalRequest))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].status == "PENDING"


@pytest.mark.asyncio
async def test_api_120_viewer_forbidden(
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
    await _seed_viewer(db_session, org_id=org_id, project_id=project_id)
    await login_as(client, idp_subject="viewer-120")
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(project_id=project_id),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_120_undeclared_agent_pol002(
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
            action_type="agent_tool_action",
            payload={},
        ),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-POL-002"


@pytest.mark.asyncio
async def test_api_120_unknown_action_pol002(
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
    body = _preview_body(project_id=project_id)
    body["action_type"] = "not_a_real_action"
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_120_copilot_write_state001(
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
        json=_preview_body(project_id=project_id, action_type="copilot_write"),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_120_client_param_hash_val001(
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
        json=_preview_body(project_id=project_id, extra={"param_hash": "forged"}),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_120_missing_idempotency_key(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    response = await client.post(
        "/api/v1/action-previews",
        json=_preview_body(project_id=project_id),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_120_l3_stale_reauth_no_approval(
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
    await _stale_session(db_session, client)
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(project_id=project_id, action_type="env_register"),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-002"
    result = await db_session.execute(select(ApprovalRequest))
    assert len(list(result.scalars().all())) == 0


@pytest.mark.asyncio
async def test_api_120_after_reauth_require_approval(
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
    await _stale_session(db_session, client)
    key = str(uuid.uuid4())
    body = _preview_body(project_id=project_id, action_type="env_register")
    stale = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert stale.status_code == 401
    await _fresh_reauth(db_session, client)
    replay = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["gate"] == "REQUIRE_APPROVAL"


@pytest.mark.asyncio
async def test_api_120_idempotent_same_key_same_hash(
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
    key = str(uuid.uuid4())
    body = _preview_body(project_id=project_id)
    first = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=body,
    )
    second = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


@pytest.mark.asyncio
async def test_api_120_idempotent_same_key_different_hash(
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
    key = str(uuid.uuid4())
    first = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=_preview_body(project_id=project_id),
    )
    second = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": key},
        json=_preview_body(project_id=project_id, payload={"summary": "changed"}),
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "HT-IDEM-001"


@pytest.mark.asyncio
async def test_api_120_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    response = await client.post(
        "/api/v1/action-previews",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_preview_body(project_id=project_id),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"
