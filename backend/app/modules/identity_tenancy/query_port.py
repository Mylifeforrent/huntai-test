"""Cross-module read-only queries for identity_tenancy (no ORM export to consumers)."""

import uuid
from copy import deepcopy
from typing import Any

from sqlalchemy import and_, distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Project,
    ProjectMember,
    User,
)


async def get_capability_controls(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any]:
    org = await repo.get_organization_by_id(session, organization_id)
    if org is None:
        return deepcopy(DEFAULT_CAPABILITY_CONTROLS)
    controls = deepcopy(org.capability_controls)
    for key, default in DEFAULT_CAPABILITY_CONTROLS.items():
        controls.setdefault(key, deepcopy(default) if isinstance(default, list) else default)
    return controls


async def project_exists_in_org(
    session: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(Project.id).where(
            Project.organization_id == organization_id,
            Project.id == project_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_project_membership_role(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str | None:
    result = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    role = result.scalar_one_or_none()
    return str(role) if role is not None else None


async def list_project_owner_admin_user_ids(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    exclude_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    result = await session.execute(
        select(ProjectMember.user_id).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.role.in_(("owner", "admin")),
            ProjectMember.user_id != exclude_user_id,
        )
    )
    return list(result.scalars().all())


async def list_org_owner_admin_user_ids(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    exclude_user_id: uuid.UUID,
) -> list[uuid.UUID]:
    result = await session.execute(
        select(distinct(ProjectMember.user_id))
        .select_from(ProjectMember)
        .join(
            User,
            and_(
                User.id == ProjectMember.user_id,
                User.organization_id == ProjectMember.organization_id,
            ),
        )
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.role.in_(("owner", "admin")),
            ProjectMember.user_id != exclude_user_id,
            User.is_disabled.is_(False),
        )
    )
    return list(result.scalars().all())


async def caller_has_non_viewer_role(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
            ProjectMember.role.in_(("owner", "admin", "tester")),
        )
    )
    return result.first() is not None


async def list_user_project_memberships(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[tuple[uuid.UUID, str]]:
    result = await session.execute(
        select(ProjectMember.project_id, ProjectMember.role).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
        )
    )
    return [(row[0], str(row[1])) for row in result.all()]


async def users_share_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id_a: uuid.UUID,
    user_id_b: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(ProjectMember.project_id)
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id_a,
        )
        .intersect(
            select(ProjectMember.project_id).where(
                ProjectMember.organization_id == organization_id,
                ProjectMember.user_id == user_id_b,
            )
        )
    )
    return result.first() is not None


async def caller_is_owner_or_admin(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
            ProjectMember.role.in_(("owner", "admin")),
        )
    )
    return result.first() is not None


async def get_project_jira_project_key(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> str | None:
    result = await session.execute(
        select(Project.jira_project_key).where(
            Project.organization_id == organization_id,
            Project.id == project_id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        return None
    stripped = str(key).strip()
    return stripped or None


async def caller_is_owner(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await session.execute(
        select(ProjectMember.role).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
            ProjectMember.role == "owner",
        )
    )
    return result.first() is not None
