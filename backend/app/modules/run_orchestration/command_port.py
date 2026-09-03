"""Cross-module commands for run_orchestration (no ORM export to consumers)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.run_orchestration import repository as repo


async def merge_clustering_projection(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    clustering: dict[str, Any],
) -> None:
    """Merge clustering projection into TestRun.result_summary without touching snapshot."""
    run = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        for_update=True,
    )
    if run is None:
        raise ValueError("not_found")
    summary = dict(run.result_summary or {})
    summary["clustering"] = clustering
    run.result_summary = summary
    await session.flush()
