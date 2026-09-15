"""API-170/171/172 ApiToken management tests."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    DEFAULT_SIEM_EXPORT,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.modules.integration_hub.service import authenticate_api_token
from tests.helpers import login_as
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case


async def _seed_tester(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "tester-api-token",
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
            display_name="Tester",
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
            role="tester",
        )
    )
    await db_session.commit()
    return user_id


def _issue_body(
    *,
    project_id: uuid.UUID,
    scopes: list[str] | None = None,
) -> dict[str, object]:
    expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    return {
        "scopes": scopes if scopes is not None else ["read"],
        "project_ids": [str(project_id)],
        "expires_at": expires_at,
    }


async def _issue_token(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    scopes: list[str] | None = None,
) -> tuple[str, str]:
    issue = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=scopes),
    )
    assert issue.status_code == 200
    issued = issue.json()["data"]
    plaintext = issued["token"]
    token_id = issued["id"]
    return plaintext, token_id


async def _get_token_list_item(client: AsyncClient, token_id: str) -> dict[str, object]:
    list_resp = await client.get("/api/v1/api-tokens")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    return next(item for item in items if item["id"] == token_id)


@pytest.mark.asyncio
async def test_api_170_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/api-tokens")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_170_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_tester(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client, idp_subject="tester-api-token")
    response = await client.get("/api/v1/api-tokens")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_171_empty_project_ids_validation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    response = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"scopes": ["read"], "project_ids": [], "expires_at": expires_at},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_171_unperceivable_project_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _ = seeded_identity
    await login_as(client)
    expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    response = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "scopes": ["read"],
            "project_ids": [str(uuid.uuid4())],
            "expires_at": expires_at,
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_171_issue_list_revoke_and_authenticate(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)

    idem_key = str(uuid.uuid4())
    expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    issue_body = {
        "scopes": ["read"],
        "project_ids": [str(project_id)],
        "expires_at": expires_at,
    }
    issue = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": idem_key},
        json=issue_body,
    )
    assert issue.status_code == 200
    issued = issue.json()["data"]
    assert "token" in issued
    plaintext = issued["token"]
    assert issued["token_prefix"]
    token_id = issued["id"]

    replay = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": idem_key},
        json=issue_body,
    )
    assert replay.status_code == 200
    replay_data = replay.json()["data"]
    assert "token" not in replay_data
    assert replay_data["id"] == token_id

    list_resp = await client.get("/api/v1/api-tokens")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    match = next(item for item in items if item["id"] == token_id)
    assert "token" not in match
    assert "token_hash" not in match
    assert match["token_prefix"] == issued["token_prefix"]

    authenticated = await authenticate_api_token(
        db_session,
        organization_id=org_id,
        raw_token=plaintext,
    )
    assert authenticated is not None
    assert authenticated.id == uuid.UUID(token_id)

    revoke = await client.post(
        f"/api/v1/api-tokens/{token_id}/revocations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert revoke.status_code == 200
    assert revoke.json()["data"]["revoked_at"]

    db_session.expire_all()
    failed = await authenticate_api_token(
        db_session,
        organization_id=org_id,
        raw_token=plaintext,
    )
    assert failed is None


@pytest.mark.asyncio
async def test_api_172_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    other_org_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    now = datetime.now(UTC)
    db_session.add(
        Organization(
            id=other_org_id,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other Org",
            slug="other-org",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            siem_export=dict(DEFAULT_SIEM_EXPORT),
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=other_user_id,
            organization_id=other_org_id,
            created_at=now,
            updated_at=now,
            created_by=other_user_id,
            aggregate_version=1,
            idp_subject="other-owner",
            display_name="Other",
            email="other@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=other_project_id,
            organization_id=other_org_id,
            created_at=now,
            updated_at=now,
            created_by=other_user_id,
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
            organization_id=other_org_id,
            created_at=now,
            updated_at=now,
            created_by=other_user_id,
            aggregate_version=1,
            project_id=other_project_id,
            user_id=other_user_id,
            role="owner",
        )
    )
    await db_session.commit()

    await login_as(client, idp_subject="other-owner")
    other_issue = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=other_project_id),
    )
    other_token_id = other_issue.json()["data"]["id"]

    await login_as(client)
    response = await client.post(
        f"/api/v1/api-tokens/{other_token_id}/revocations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_170_last_used_at_null_after_issue(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    _plaintext, token_id = await _issue_token(client, project_id=project_id)
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"] is None


@pytest.mark.asyncio
async def test_api_170_last_used_at_set_after_read_token_call(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    plaintext, token_id = await _issue_token(client, project_id=project_id, scopes=["read"])
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"] is None

    client.cookies.clear()
    read_resp = await client.get(
        "/api/v1/test-runs",
        headers={"Authorization": f"Bearer {plaintext}"},
        params={"project_id": str(project_id)},
    )
    assert read_resp.status_code == 200

    await login_as(client)
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"]
    datetime.fromisoformat(str(item["last_used_at"]))


@pytest.mark.asyncio
async def test_api_170_last_used_at_set_after_execute_token_post(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    plaintext, token_id = await _issue_token(client, project_id=project_id, scopes=["execute"])
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"] is None

    client.cookies.clear()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    with patch("app.modules.run_orchestration.executor.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_client
        response = await client.post(
            "/api/v1/test-runs",
            headers={
                "Idempotency-Key": str(uuid.uuid4()),
                "Authorization": f"Bearer {plaintext}",
            },
            json={
                "project_id": str(project_id),
                "env_id": env["id"],
                "execution_source": "script",
                "case_ids": [case["id"]],
                "params": {"TARGET_ENV": "https://example.test"},
            },
        )
    assert response.status_code == 200

    await login_as(client)
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"]
    datetime.fromisoformat(str(item["last_used_at"]))


@pytest.mark.asyncio
async def test_api_170_last_used_at_unchanged_on_bad_bearer(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    _plaintext, token_id = await _issue_token(client, project_id=project_id)

    client.cookies.clear()
    bad_resp = await client.get(
        "/api/v1/test-runs",
        headers={"Authorization": "Bearer ht_live_invalid_token_value"},
        params={"project_id": str(project_id)},
    )
    assert bad_resp.status_code == 401

    await login_as(client)
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"] is None


@pytest.mark.asyncio
async def test_api_170_last_used_at_unchanged_on_revoked_token(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    plaintext, token_id = await _issue_token(client, project_id=project_id)

    revoke = await client.post(
        f"/api/v1/api-tokens/{token_id}/revocations",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert revoke.status_code == 200

    client.cookies.clear()
    read_resp = await client.get(
        "/api/v1/test-runs",
        headers={"Authorization": f"Bearer {plaintext}"},
        params={"project_id": str(project_id)},
    )
    assert read_resp.status_code == 401

    await login_as(client)
    item = await _get_token_list_item(client, token_id)
    assert item["last_used_at"] is None
