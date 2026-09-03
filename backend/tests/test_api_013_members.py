import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import ProjectMember, User
from tests.helpers import login_as


async def _add_member(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    role: str,
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
async def test_api_013_happy_owner_sees_email(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    await login_as(client)
    project_id = seeded_identity["project_id"]
    response = await client.get(f"/api/v1/projects/{project_id}/members")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert "email" in items[0]
    assert items[0]["email"] == "user@example.com"
    assert items[0]["role"] == "owner"


@pytest.mark.asyncio
async def test_api_013_email_omitted_for_tester(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await _add_member(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="tester",
        idp_subject="tester-013",
        email="tester013@example.com",
    )
    await login_as(client, idp_subject="tester-013")
    response = await client.get(f"/api/v1/projects/{project_id}/members")
    assert response.status_code == 200
    for item in response.json()["data"]["items"]:
        assert "email" not in item


@pytest.mark.asyncio
async def test_api_013_email_omitted_for_viewer(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await _add_member(
        db_session,
        org_id=org_id,
        project_id=project_id,
        role="viewer",
        idp_subject="viewer-013",
        email="viewer013@example.com",
    )
    await login_as(client, idp_subject="viewer-013")
    response = await client.get(f"/api/v1/projects/{project_id}/members")
    assert response.status_code == 200
    for item in response.json()["data"]["items"]:
        assert "email" not in item


@pytest.mark.asyncio
async def test_api_013_non_member_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
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
            idp_subject="nm-013",
            display_name="NM",
            email="nm013@example.com",
            is_disabled=False,
        )
    )
    await db_session.commit()
    await login_as(client, idp_subject="nm-013")
    response = await client.get(f"/api/v1/projects/{project_id}/members")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
