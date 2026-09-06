"""PerfBaseline read/write services (API-056…059, FR-11 / S-M3-01).

Baselines are scenario-scoped: exactly one active baseline per
case_type=performance TestCase; creating a new active baseline CAS-deactivates
the previous one. Metrics snapshots are frozen after creation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.test_assets import repository as repo
from app.modules.test_assets.models import PerfBaseline

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})
COMMAND_CREATE = "perf_baseline.create"
COMMAND_DEACTIVATE = "perf_baseline.deactivate"


async def _require_scenario_access(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    scenario_test_case_id: uuid.UUID,
    roles: frozenset[str],
) -> str:
    case = await repo.get_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=scenario_test_case_id,
    )
    if case is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=case.project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in roles:
        raise ValueError("not_found")
    return str(case.case_type)


def serialize_perf_baseline(row: PerfBaseline) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "scenario_test_case_id": str(row.scenario_test_case_id),
        "is_active": row.is_active,
        "version": row.aggregate_version,
        "metrics_snapshot": dict(row.metrics_snapshot or {}),
        "tolerance": dict(row.tolerance or {}),
        "latest_run_id": str(row.latest_run_id) if row.latest_run_id else None,
        "created_at": row.created_at.isoformat(),
        "created_by": str(row.created_by) if row.created_by else None,
    }


async def list_perf_baselines_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    scenario_test_case_id: uuid.UUID,
) -> dict[str, Any]:
    case_type = await _require_scenario_access(
        session, ctx, scenario_test_case_id=scenario_test_case_id, roles=READ_ROLES
    )
    _ = case_type
    rows = await repo.list_perf_baselines(
        session,
        organization_id=ctx.organization.id,
        scenario_test_case_id=scenario_test_case_id,
    )
    return {"items": [serialize_perf_baseline(row) for row in rows], "page": {"has_more": False}}


async def get_perf_baseline_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    perf_baseline_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_perf_baseline(
        session,
        organization_id=ctx.organization.id,
        perf_baseline_id=perf_baseline_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_scenario_access(
        session, ctx, scenario_test_case_id=row.scenario_test_case_id, roles=READ_ROLES
    )
    payload = serialize_perf_baseline(row)
    payload["comparison"] = {
        "baseline_metrics": dict(row.metrics_snapshot or {}),
        "tolerance": dict(row.tolerance or {}),
        "latest_run_id": str(row.latest_run_id) if row.latest_run_id else None,
    }
    return payload


async def create_perf_baseline_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    scenario_test_case_id: uuid.UUID,
    metrics_snapshot: dict[str, Any],
    tolerance: dict[str, Any],
    expected_active_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    case_type = await _require_scenario_access(
        session, ctx, scenario_test_case_id=scenario_test_case_id, roles=WRITE_ROLES
    )
    if case_type != "performance":
        raise ValueError("validation")

    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    old_active = await repo.get_active_perf_baseline_for_scenario(
        session,
        organization_id=ctx.organization.id,
        scenario_test_case_id=scenario_test_case_id,
    )
    if old_active is not None:
        if (
            expected_active_version is not None
            and old_active.aggregate_version != expected_active_version
        ):
            raise ValueError("version")
        old_active.is_active = False
        old_active.aggregate_version += 1
        old_active.updated_at = datetime.now(UTC)
        await session.flush()

    now = datetime.now(UTC)
    row = PerfBaseline(
        id=uuid.uuid4(),
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        aggregate_version=1,
        scenario_test_case_id=scenario_test_case_id,
        is_active=True,
        metrics_snapshot=metrics_snapshot,
        tolerance=tolerance,
        latest_run_id=None,
    )
    session.add(row)
    await session.flush()
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="perf_baseline.create",
            resource_type="perf_baseline",
            resource_id=row.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    payload = serialize_perf_baseline(row)
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    return payload


async def deactivate_perf_baseline_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    perf_baseline_id: uuid.UUID,
    expected_version: int,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_perf_baseline(
        session,
        organization_id=ctx.organization.id,
        perf_baseline_id=perf_baseline_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_scenario_access(
        session, ctx, scenario_test_case_id=row.scenario_test_case_id, roles=WRITE_ROLES
    )
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_DEACTIVATE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})
    if row.aggregate_version != expected_version:
        raise ValueError("version")
    row.is_active = False
    row.aggregate_version += 1
    row.updated_at = datetime.now(UTC)
    await session.flush()
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="perf_baseline.deactivate",
            resource_type="perf_baseline",
            resource_id=row.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    payload = serialize_perf_baseline(row)
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_DEACTIVATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=datetime.now(UTC),
    )
    return payload
