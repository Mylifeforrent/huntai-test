"""Cross-module commands for execution_registry (no ORM export to consumers)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import repository as repo


async def activate_after_env_register(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
) -> None:
    """CAS PENDING_APPROVAL → ACTIVE after env_register approval executes."""
    env = await repo.get_environment(
        session,
        organization_id=organization_id,
        environment_id=environment_id,
        for_update=True,
    )
    if env is None:
        raise ValueError("not_found")
    if env.status != "PENDING_APPROVAL":
        raise ValueError("state")
    now = datetime.now(UTC)
    env.status = "ACTIVE"
    env.updated_at = now
    env.aggregate_version += 1
    env.config_version = env.aggregate_version
    await session.flush()
