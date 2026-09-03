"""Cross-module read-only queries for results_evidence."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import repository as repo


async def get_failure_cluster_confidence(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    failure_cluster_id: uuid.UUID,
) -> float | None:
    row = await repo.get_failure_cluster(
        session,
        organization_id=organization_id,
        failure_cluster_id=failure_cluster_id,
    )
    if row is None:
        return None
    return float(row.confidence)
