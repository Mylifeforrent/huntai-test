import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quota_governance.models import OrgQuota


async def get_org_quota(session: AsyncSession, *, organization_id: uuid.UUID) -> OrgQuota | None:
    result = await session.execute(
        select(OrgQuota).where(OrgQuota.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def get_org_quota_for_update(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> OrgQuota | None:
    result = await session.execute(
        select(OrgQuota).where(OrgQuota.organization_id == organization_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def create_org_quota(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    token_budget: Decimal,
    token_reserved: Decimal,
    token_consumed: Decimal,
    executor_slot_quota: int,
    perf_concurrency_quota: int,
) -> OrgQuota:
    row = OrgQuota(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        token_budget=token_budget,
        token_reserved=token_reserved,
        token_consumed=token_consumed,
        executor_slot_quota=executor_slot_quota,
        perf_concurrency_quota=perf_concurrency_quota,
    )
    session.add(row)
    await session.flush()
    return row
