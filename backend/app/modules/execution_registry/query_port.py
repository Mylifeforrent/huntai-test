"""Cross-module read-only queries for execution_registry (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import repository as repo


async def get_environment_for_start(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
) -> dict[str, Any] | None:
    env = await repo.get_environment(
        session,
        organization_id=organization_id,
        environment_id=environment_id,
    )
    if env is None:
        return None
    return {
        "status": env.status,
        "version": env.aggregate_version,
        "config_version": env.config_version,
        "env_type": env.env_type,
        "scope_level": env.scope_level,
        "project_id": env.project_id,
    }
