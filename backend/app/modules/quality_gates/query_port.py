"""Cross-module read-only queries for quality_gates (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.service import serialize_detail


async def get_policy_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_policy_for_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
    )
    if row is None:
        return None
    return serialize_detail(row)
