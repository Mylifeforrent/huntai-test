"""Cross-module commands for quota_governance (no ORM export to consumers)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quota_governance.models import OrgQuota


async def reserve_perf_concurrency(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    slots: int = 1,
) -> bool:
    """Reserve perf concurrency slots with a row lock; False = HT-QUOTA-001."""
    result = await session.execute(
        select(OrgQuota).where(OrgQuota.organization_id == organization_id).with_for_update()
    )
    quota = result.scalar_one_or_none()
    if quota is None:
        return False
    if quota.perf_concurrency_in_use + slots > quota.perf_concurrency_quota:
        return False
    quota.perf_concurrency_in_use += slots
    quota.updated_at = quota.updated_at
    await session.flush()
    return True


async def release_perf_concurrency(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    slots: int = 1,
) -> None:
    result = await session.execute(
        select(OrgQuota).where(OrgQuota.organization_id == organization_id).with_for_update()
    )
    quota = result.scalar_one_or_none()
    if quota is None:
        return
    quota.perf_concurrency_in_use = max(0, quota.perf_concurrency_in_use - slots)
    await session.flush()


async def get_perf_concurrency_projection(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> dict[str, int] | None:
    result = await session.execute(
        select(OrgQuota).where(OrgQuota.organization_id == organization_id)
    )
    quota = result.scalar_one_or_none()
    if quota is None:
        return None
    return {
        "perf_concurrency_quota": quota.perf_concurrency_quota,
        "perf_concurrency_in_use": quota.perf_concurrency_in_use,
    }
