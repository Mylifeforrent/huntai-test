import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)
from tests.helpers import login_as


async def _seed_org_user(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    idp_subject: str,
    email: str,
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
            display_name=idp_subject,
            email=email,
            is_disabled=False,
        )
    )
    await db_session.commit()
    return user_id


async def _seed_member_with_role(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    role: str,
    idp_subject: str,
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
            display_name=idp_subject,
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
            role=role,
        )
    )
    await db_session.commit()
    return user_id


@pytest.mark.asyncio
async def test_api_014_happy(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    new_user = await _seed_org_user(
        db_session, org_id=org_id, idp_subject="add-me", email="addme@example.com"
    )
    await login_as(client)
    key = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": key},
        json={"user_id": str(new_user), "role": "tester"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user_id"] == str(new_user)
    assert data["role"] == "tester"
    assert data["project_id"] == str(project_id)

    listed = await client.get(f"/api/v1/projects/{project_id}/members")
    user_ids = {item["user_id"] for item in listed.json()["data"]["items"]}
    assert str(new_user) in user_ids


@pytest.mark.asyncio
async def test_api_014_missing_idempotency_key(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    new_user = await _seed_org_user(
        db_session, org_id=org_id, idp_subject="no-key", email="nokey@example.com"
    )
    await login_as(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": str(new_user), "role": "viewer"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_014_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await _seed_member_with_role(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="tester",
        idp_subject="tester-014",
    )
    target = await _seed_org_user(
        db_session, org_id=org_id, idp_subject="target-014", email="t014@example.com"
    )
    await login_as(client, idp_subject="tester-014")
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"user_id": str(target), "role": "viewer"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_014_duplicate_pair_no_silent_role_change(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    existing = await _seed_member_with_role(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="viewer",
        idp_subject="dup-014",
    )
    await login_as(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"user_id": str(existing), "role": "admin"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"

    listed = await client.get(f"/api/v1/projects/{project_id}/members")
    roles = {item["user_id"]: item["role"] for item in listed.json()["data"]["items"]}
    assert roles[str(existing)] == "viewer"


@pytest.mark.asyncio
async def test_api_014_idempotent_retry_same_key_same_hash(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    new_user = await _seed_org_user(
        db_session, org_id=org_id, idp_subject="idem-014", email="idem014@example.com"
    )
    await login_as(client)
    key = str(uuid.uuid4())
    body = {"user_id": str(new_user), "role": "admin"}
    first = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": key},
        json=body,
    )
    second = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


@pytest.mark.asyncio
async def test_api_014_other_org_user_val(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other",
            slug="other-014",
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
            idp_subject="foreign-014",
            display_name="Foreign",
            email="foreign014@example.com",
            is_disabled=False,
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"user_id": str(other_user), "role": "viewer"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_014_cross_tenant_project_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
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
            name="XOrg",
            slug="xorg-014",
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
            idp_subject="xorg-014",
            display_name="X",
            email="x014@example.com",
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
            name="X Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.commit()

    local_user = await _seed_org_user(
        db_session, org_id=org_id, idp_subject="local-014", email="local014@example.com"
    )
    await login_as(client)
    response = await client.post(
        f"/api/v1/projects/{other_project}/members",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"user_id": str(local_user), "role": "viewer"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
