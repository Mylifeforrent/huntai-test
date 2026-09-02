"""Cross-module read-only queries for ai_governance (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance import repository as repo


async def get_generation_drafts(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    generation_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_a1_generation(
        session,
        organization_id=organization_id,
        generation_id=generation_id,
    )
    if row is None or row.project_id != project_id:
        return None
    if row.status not in {"succeeded", "partial"}:
        return None
    return {
        "generation_id": row.id,
        "status": row.status,
        "cases": row.drafts or [],
        "failed_items": row.failed_items or [],
        "degraded": row.degraded,
    }


async def get_generation_status(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    generation_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_a1_generation(
        session,
        organization_id=organization_id,
        generation_id=generation_id,
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "status": row.status,
        "project_id": row.project_id,
        "accepted_at": row.accepted_at,
        "completed_at": row.completed_at,
        "degraded": row.degraded,
        "drafts": row.drafts,
        "failed_items": row.failed_items,
        "error": row.error,
        "invocation_log_id": row.invocation_log_id,
    }
