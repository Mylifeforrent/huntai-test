import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import ProjectMember, User
from tests.helpers import login_as


async def _seed_member(
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
async def test_api_016_remove_member(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    member_id = await _seed_member(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="viewer",
        idp_subject="remove-016",
    )
    await login_as(client)
    key = str(uuid.uuid4())
    response = await client.delete(
        f"/api/v1/projects/{project_id}/members/{member_id}",
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 204

    listed = await client.get(f"/api/v1/projects/{project_id}/members")
    ids = {item["user_id"] for item in listed.json()["data"]["items"]}
    assert str(member_id) not in ids


@pytest.mark.asyncio
async def test_api_016_last_owner_remove_state(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    await login_as(client)
    response = await client.delete(
        f"/api/v1/projects/{project_id}/members/{user_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_016_idempotent_repeat_same_key(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    member_id = await _seed_member(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="admin",
        idp_subject="idem-remove-016",
    )
    await login_as(client)
    key = str(uuid.uuid4())
    first = await client.delete(
        f"/api/v1/projects/{project_id}/members/{member_id}",
        headers={"Idempotency-Key": key},
    )
    second = await client.delete(
        f"/api/v1/projects/{project_id}/members/{member_id}",
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 204
    assert second.status_code == 204


@pytest.mark.asyncio
async def test_api_016_missing_member_new_key_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    project_id = seeded_identity["project_id"]
    await login_as(client)
    response = await client.delete(
        f"/api/v1/projects/{project_id}/members/{uuid.uuid4()}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
