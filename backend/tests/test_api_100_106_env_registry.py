import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest
from app.modules.identity_tenancy.models import ProjectMember, User
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_admin_peer


def _register_body(
    *,
    project_id: uuid.UUID,
    name: str = "CI Staging",
    scope_level: str = "organization",
    job_contracts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "env_type": "external_ci",
        "name": name,
        "scope_level": scope_level,
        "project_id": str(project_id),
        "endpoint": "https://ci.example.com",
    }
    if job_contracts is not None:
        body["job_contracts"] = job_contracts
    return body


async def _register_environment(
    client: AsyncClient,
    project_id: uuid.UUID,
    *,
    name: str = "CI Staging",
    scope_level: str = "organization",
    job_contracts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/execution-environments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_register_body(
            project_id=project_id,
            name=name,
            scope_level=scope_level,
            job_contracts=job_contracts,
        ),
    )
    assert response.status_code == 200
    return response.json()["data"]


async def _seed_tester(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "tester-env",
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


@pytest.mark.asyncio
async def test_api_100_list_after_register_no_credential_ref(
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
    created = await _register_environment(client, project_id, name="List Env")
    assert created["status"] == "PENDING_APPROVAL"

    response = await client.get("/api/v1/execution-environments")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    match = next(item for item in items if item["id"] == created["id"])
    assert match["status"] == "PENDING_APPROVAL"
    assert "credential_ref" not in match
    assert "credential_present" in match


@pytest.mark.asyncio
async def test_api_102_tester_register_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_tester(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client, idp_subject="tester-env")
    response = await client.post(
        "/api/v1/execution-environments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_register_body(project_id=project_id),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_101_other_org_not_found(
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
    created = await _register_environment(client, project_id)
    other_id = uuid.uuid4()
    response = await client.get(f"/api/v1/execution-environments/{other_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
    detail = await client.get(f"/api/v1/execution-environments/{created['id']}")
    assert detail.status_code == 200


@pytest.mark.asyncio
async def test_api_102_forbidden_status_active_policy_deny(
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
    body = _register_body(project_id=project_id)
    body["status"] = "ACTIVE"
    response = await client.post(
        "/api/v1/execution-environments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_api_102_invalid_preview_policy_deny(
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
    body = _register_body(project_id=project_id)
    body["preview_id"] = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/execution-environments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-POL-001"


@pytest.mark.asyncio
async def test_api_102_register_pending_approval_with_approval_row(
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
    created = await _register_environment(client, project_id)
    assert created["status"] == "PENDING_APPROVAL"
    assert created["status"] != "ACTIVE"
    assert "approval_request_id" in created

    approvals = await db_session.execute(
        select(ApprovalRequest).where(ApprovalRequest.action_type == "env_register")
    )
    rows = list(approvals.scalars().all())
    assert len(rows) == 1
    assert rows[0].status == "PENDING"


@pytest.mark.asyncio
async def test_api_112_approve_env_register_activates_environment(
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
    created = await _register_environment(client, project_id)
    approval_id = created["approval_request_id"]

    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    decision = await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["status"] == "EXECUTED"

    await login_as(client)
    env = await client.get(f"/api/v1/execution-environments/{created['id']}")
    assert env.status_code == 200
    assert env.json()["data"]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_api_103_disable_cas_and_idempotent(
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
    created = await _register_environment(client, project_id)
    approval_id = created["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )

    await login_as(client)
    env_detail = await client.get(f"/api/v1/execution-environments/{created['id']}")
    env_version = env_detail.json()["data"]["version"]
    key = str(uuid.uuid4())
    body = {"expected_version": env_version}
    first = await client.post(
        f"/api/v1/execution-environments/{created['id']}/disable",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200
    assert first.json()["data"]["status"] == "DISABLED"
    second = await client.post(
        f"/api/v1/execution-environments/{created['id']}/disable",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "DISABLED"


@pytest.mark.asyncio
async def test_api_104_070_job_contracts_and_unknown_job(
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
    job_contracts = [
        {
            "job_id": "smoke-suite",
            "supports_cancel": True,
            "contract_version": 1,
            "schema": {"type": "object", "properties": {"branch": {"type": "string"}}},
        }
    ]
    created = await _register_environment(client, project_id, job_contracts=job_contracts)
    env_id = created["id"]

    jobs = await client.get(f"/api/v1/execution-environments/{env_id}/jobs")
    assert jobs.status_code == 200
    job_items = jobs.json()["data"]["items"]
    assert len(job_items) == 1
    assert job_items[0]["job_id"] == "smoke-suite"

    schema = await client.get(
        f"/api/v1/execution-environments/{env_id}/jobs/smoke-suite/params-schema"
    )
    assert schema.status_code == 200
    data = schema.json()["data"]
    assert data["job_id"] == "smoke-suite"
    assert data["schema"]["type"] == "object"

    missing = await client.get(
        f"/api/v1/execution-environments/{env_id}/jobs/unknown-job/params-schema"
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_105_health_projection(
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
    created = await _register_environment(client, project_id)
    response = await client.get(f"/api/v1/execution-environments/{created['id']}/health")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["environment_id"] == created["id"]
    assert data["status"] == "PENDING_APPROVAL"
    assert "environment_version" in data


@pytest.mark.asyncio
async def test_api_106_unknown_connector_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.post(
        f"/api/v1/connectors/{uuid.uuid4()}/credential-refs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"credential_ref": "ref-only", "expected_version": 1},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_100_unauthenticated(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/execution-environments")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"
