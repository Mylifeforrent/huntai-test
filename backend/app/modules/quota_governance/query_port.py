"""Cross-module read-only queries for quota_governance (no ORM export to consumers)."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quota_governance import repository as repo
from app.modules.quota_governance.service import serialize_org_quota


async def get_current_quota(
    session: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await repo.get_org_quota(session, organization_id=organization_id)
    if row is None:
        return None
    return serialize_org_quota(row)


async def token_budget_exhausted(session: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    row = await repo.get_org_quota(session, organization_id=organization_id)
    if row is None:
        return True
    remaining = row.token_budget - row.token_reserved - row.token_consumed
    return remaining <= Decimal("0")
