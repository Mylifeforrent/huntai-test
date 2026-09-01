"""Idempotent local identity seed for mock IdP. Not a product bootstrap path."""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.db import dispose_engine, get_session_factory
from app.modules.ai_governance.service import seed_default_model_routes
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)

ORG_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
PROJECT_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
MEMBER_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
USER2_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")
IDP_SUBJECT = "local-dev-user"
IDP_SUBJECT_2 = "local-dev-user-2"
ORG_SLUG = "local-dev"


async def seed() -> None:
    factory = get_session_factory()
    now = datetime.now(UTC)
    async with factory() as session:
        org = await session.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
        if org is None:
            org = Organization(
                id=ORG_ID,
                created_at=now,
                updated_at=now,
                created_by=None,
                aggregate_version=1,
                name="Local Dev Org",
                slug=ORG_SLUG,
                capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
                is_active=True,
            )
            session.add(org)
            await session.flush()

        user = await session.scalar(select(User).where(User.id == USER_ID))
        if user is None:
            user = User(
                id=USER_ID,
                organization_id=org.id,
                created_at=now,
                updated_at=now,
                created_by=USER_ID,
                aggregate_version=1,
                idp_subject=IDP_SUBJECT,
                display_name="Local Dev User",
                email="local-dev@example.test",
                is_disabled=False,
            )
            session.add(user)
            await session.flush()
        else:
            user.idp_subject = IDP_SUBJECT
            user.is_disabled = False

        project = await session.scalar(select(Project).where(Project.id == PROJECT_ID))
        if project is None:
            session.add(
                Project(
                    id=PROJECT_ID,
                    organization_id=org.id,
                    created_at=now,
                    updated_at=now,
                    created_by=USER_ID,
                    aggregate_version=1,
                    name="Local Dev Project",
                    jira_project_key=None,
                    jira_sync_cursor=None,
                    bind_env_ids=None,
                )
            )
            await session.flush()

        member = await session.scalar(select(ProjectMember).where(ProjectMember.id == MEMBER_ID))
        if member is None:
            session.add(
                ProjectMember(
                    id=MEMBER_ID,
                    organization_id=org.id,
                    created_at=now,
                    updated_at=now,
                    created_by=USER_ID,
                    aggregate_version=1,
                    project_id=PROJECT_ID,
                    user_id=USER_ID,
                    role="owner",
                )
            )

        user2 = await session.scalar(select(User).where(User.id == USER2_ID))
        if user2 is None:
            session.add(
                User(
                    id=USER2_ID,
                    organization_id=org.id,
                    created_at=now,
                    updated_at=now,
                    created_by=USER_ID,
                    aggregate_version=1,
                    idp_subject=IDP_SUBJECT_2,
                    display_name="Local Dev User 2",
                    email="local-dev-2@example.test",
                    is_disabled=False,
                )
            )
        else:
            user2.idp_subject = IDP_SUBJECT_2
            user2.is_disabled = False

        await seed_default_model_routes(session, organization_id=org.id, created_by=USER_ID)

        await session.commit()
    await dispose_engine()
    print(f"seeded org={ORG_SLUG} idp_subject={IDP_SUBJECT} user2={USER2_ID}")


if __name__ == "__main__":
    asyncio.run(seed())
