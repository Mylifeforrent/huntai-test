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
async def test_api_012_happy(
    client: AsyncClient,
    seeded_identity: dict[str, object],
) -> None:
    await login_as(client)
    project_id = seeded_identity["project_id"]
    response = await client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == str(project_id)
    assert data["name"] == "Test Project"
    assert data["my_role"] == "owner"
    assert data["jira"] == {"project_key": None}
    assert data["connector_health"] == []
    assert isinstance(data["recent_activity"], list)
    assert "jira_sync_cursor" not in data
    assert "credential_ref" not in data
    text = response.text
    assert "jira_sync_cursor" not in text
    assert "secret" not in text.lower() or "secret" not in data.get("name", "").lower()


@pytest.mark.asyncio
async def test_api_012_non_member_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    project_id = seeded_identity["project_id"]
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject="non-member-subject",
            display_name="Non Member",
            email="nonmember@example.com",
            is_disabled=False,
        )
    )
    await db_session.commit()

    await login_as(client, idp_subject="non-member-subject")
    response = await client.get(f"/api/v1/projects/{project_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_012_cross_tenant_404(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    _ = seeded_identity
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
            slug="other-org-012",
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
            idp_subject="other-012",
            display_name="Other",
            email="o012@example.com",
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
            name="Foreign",
            jira_project_key=None,
            jira_sync_cursor="cursor",
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
    response = await client.get(f"/api/v1/projects/{other_project}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
