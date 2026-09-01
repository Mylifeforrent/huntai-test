"""Shared helpers for ai_governance API tests."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.service import seed_default_model_routes
from app.modules.identity_tenancy.models import ProjectMember, User


async def seed_model_routes(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict[str, object]]:
    routes = await seed_default_model_routes(db_session, organization_id=org_id, created_by=user_id)
    await db_session.commit()
    return [
        {
            "id": route.id,
            "task_type": route.task_type,
            "data_classification": route.data_classification,
            "version": route.aggregate_version,
        }
        for route in routes
    ]


async def seed_tester(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "tester-model-routes",
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
