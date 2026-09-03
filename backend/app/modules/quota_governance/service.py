import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quota_governance import repository as repo
from app.modules.quota_governance.models import OrgQuota

DEFAULT_TOKEN_BUDGET = Decimal("1000")
DEFAULT_EXECUTOR_SLOT_QUOTA = 5
DEFAULT_PERF_CONCURRENCY_QUOTA = 2


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def compute_token_remaining(quota: OrgQuota) -> Decimal:
    return quota.token_budget - quota.token_reserved - quota.token_consumed


def serialize_org_quota(quota: OrgQuota) -> dict[str, Any]:
    remaining = compute_token_remaining(quota)
    return {
        "version": quota.aggregate_version,
        "token_budget": float(quota.token_budget),
        "token_reserved": float(quota.token_reserved),
        "token_consumed": float(quota.token_consumed),
        "token_remaining": float(remaining),
        "executor_slot_quota": quota.executor_slot_quota,
        "executor_slots_in_use": 0,
        "perf_concurrency_quota": quota.perf_concurrency_quota,
        "perf_concurrency_in_use": 0,
        "updated_at": _iso(quota.updated_at),
    }


async def seed_default_org_quota(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    token_budget: Decimal | None = None,
) -> OrgQuota:
    existing = await repo.get_org_quota(session, organization_id=organization_id)
    if existing is not None:
        return existing
    now = datetime.now(UTC)
    return await repo.create_org_quota(
        session,
        organization_id=organization_id,
        created_at=now,
        created_by=created_by,
        token_budget=token_budget if token_budget is not None else DEFAULT_TOKEN_BUDGET,
        token_reserved=Decimal("0"),
        token_consumed=Decimal("0"),
        executor_slot_quota=DEFAULT_EXECUTOR_SLOT_QUOTA,
        perf_concurrency_quota=DEFAULT_PERF_CONCURRENCY_QUOTA,
    )


async def get_current_quota_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
) -> dict[str, Any]:
    row = await repo.get_org_quota(session, organization_id=ctx.organization.id)
    if row is None:
        raise ValueError("not_found")
    return serialize_org_quota(row)


async def get_project_quota_view_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    if not await identity_query.project_exists_in_org(
        session, organization_id=org_id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None:
        raise ValueError("not_found")

    row = await repo.get_org_quota(session, organization_id=org_id)
    if row is None:
        raise ValueError("not_found")

    org_remaining = serialize_org_quota(row)
    return {
        "project_id": str(project_id),
        "org_quota_version": row.aggregate_version,
        "view": {
            "token_consumed_in_project": 0,
            "org_remaining": org_remaining,
        },
    }
