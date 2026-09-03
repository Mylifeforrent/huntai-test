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


@pytest.mark.asyncio
async def test_api_011_lists_member_projects(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    await login_as(client)
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    body = response.json()
    items = body["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["id"] == str(seeded_identity["project_id"])
    assert item["name"] == "Test Project"
    assert item["my_role"] == "owner"
    assert item["version"] == 1
    assert "jira_sync_cursor" not in item
    assert body["page"]["has_more"] is False


@pytest.mark.asyncio
async def test_api_011_unauthenticated_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_011_empty_for_user_without_memberships(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    db_session.add(
        Organization(
            id=org_id,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Lonely Org",
            slug="lonely-org",
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
            idp_subject="lonely-subject",
            display_name="Lonely",
            email="lonely@example.com",
            is_disabled=False,
        )
    )
    await db_session.commit()

    await login_as(client, idp_subject="lonely-subject")
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert response.json()["page"]["has_more"] is False


@pytest.mark.asyncio
async def test_api_011_does_not_leak_other_org_projects(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
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
            name="Other Org",
            slug="other-org",
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
            idp_subject="other-subject",
            display_name="Other",
            email="other@example.com",
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
            name="Secret Project",
            jira_project_key=None,
            jira_sync_cursor="secret-cursor",
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            user_id=other_user,
            role="owner",
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get("/api/v1/projects")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["data"]["items"]}
    assert str(seeded_identity["project_id"]) in ids
    assert str(other_project) not in ids
    for item in response.json()["data"]["items"]:
        assert "jira_sync_cursor" not in item


@pytest.mark.asyncio
async def test_api_011_sort_rejected(
    client: AsyncClient, seeded_identity: dict[str, object]
) -> None:
    _ = seeded_identity
    await login_as(client)
    response = await client.get("/api/v1/projects", params={"sort": "name"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"
