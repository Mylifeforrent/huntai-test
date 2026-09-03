"""Gate evaluation query and API service layer."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.evaluation_rules import (
    SKIP_STATUSES,
    TERMINAL_STATUSES,
    is_partial_report,
)
from app.modules.quality_gates.models import GateEvaluation
from app.modules.quality_gates.service import READ_ROLES
from app.modules.results_evidence import query_port as evidence_query
from app.modules.run_orchestration import query_port as run_query
from app.modules.run_orchestration.query_port import RunGateContext

VALID_RESULT_FILTERS = frozenset({"pass", "fail", "waived"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_list_item(row: GateEvaluation) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": _iso(row.created_at),
        "created_by": str(row.created_by) if row.created_by else None,
        "test_run_id": str(row.test_run_id),
        "policy_id": str(row.policy_id),
        "result": row.result,
        "check_run_ref": dict(row.check_run_ref) if row.check_run_ref else None,
        "waiver_approval_id": str(row.waiver_approval_id) if row.waiver_approval_id else None,
    }


def serialize_detail(row: GateEvaluation) -> dict[str, Any]:
    payload = serialize_list_item(row)
    payload["policy_snapshot"] = dict(row.policy_snapshot)
    payload["threshold_details"] = dict(row.threshold_details)
    payload["evidence_refs"] = [str(ref) for ref in row.evidence_refs]
    return payload


async def _require_project_role_for_run(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
) -> None:
    if not await identity_query.project_exists_in_org(
        session, organization_id=ctx.organization.id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        if role is None:
            raise ValueError("not_found")
        raise ValueError("forbidden")


async def _unevaluated_reason_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    run: RunGateContext,
) -> str:
    if run["execution_source"] == "agent":
        return "agent_source"
    if run["status"] in SKIP_STATUSES:
        return "cancelled_or_timeout"
    if run["status"] not in TERMINAL_STATUSES:
        return "not_terminal"
    policy = await repo.get_policy_for_project(
        session,
        organization_id=organization_id,
        project_id=run["project_id"],
    )
    if policy is None:
        return "policy_unmet"
    case_results = await evidence_query.list_case_result_outcomes_for_run(
        session,
        organization_id=organization_id,
        test_run_id=run["id"],
    )
    summary = run["result_summary"] if isinstance(run["result_summary"], dict) else None
    if is_partial_report(result_summary=summary, case_results=case_results):
        return "partial_report"
    return "not_terminal"


async def list_evaluations_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID | None,
    test_run_id: uuid.UUID | None,
    result: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    run_ids: list[uuid.UUID] | None = None
    if project_id is not None:
        await _require_project_role_for_run(session, ctx, project_id=project_id)
        run_ids = await run_query.list_run_ids_for_project(
            session,
            organization_id=ctx.organization.id,
            project_id=project_id,
        )
        if test_run_id is not None and test_run_id not in run_ids:
            run_ids = []
    elif test_run_id is not None:
        run = await run_query.get_run_for_gate(
            session,
            organization_id=ctx.organization.id,
            test_run_id=test_run_id,
        )
        if run is None:
            raise ValueError("not_found")
        await _require_project_role_for_run(session, ctx, project_id=run["project_id"])
    else:
        raise ValueError("validation")

    if result is not None and result not in VALID_RESULT_FILTERS:
        raise ValueError("validation")

    page_limit = min(limit or 50, 100)
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    rows = await repo.list_gate_evaluations(
        session,
        organization_id=ctx.organization.id,
        test_run_ids=run_ids,
        test_run_id=test_run_id,
        result_filter=result,
        created_from=created_from,
        created_to=created_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=page_limit,
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = repo.encode_created_id_cursor(created_at=last.created_at, item_id=last.id)
    return {
        "items": [serialize_list_item(row) for row in items],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_evaluation_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    evaluation_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_gate_evaluation(
        session,
        organization_id=ctx.organization.id,
        evaluation_id=evaluation_id,
    )
    if row is None:
        raise ValueError("not_found")
    run = await run_query.get_run_for_gate(
        session,
        organization_id=ctx.organization.id,
        test_run_id=row.test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    await _require_project_role_for_run(session, ctx, project_id=run["project_id"])
    return serialize_detail(row)


async def get_run_gate_evaluation_projection(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
) -> dict[str, Any]:
    run = await run_query.get_run_for_gate(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    await _require_project_role_for_run(session, ctx, project_id=run["project_id"])

    evaluation_row = await repo.get_gate_evaluation_for_run(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
    )
    if evaluation_row is None and run["gate_evaluation_id"] is None:
        reason = await _unevaluated_reason_for_run(
            session,
            organization_id=ctx.organization.id,
            run=run,
        )
        return {
            "test_run_id": str(test_run_id),
            "gate_evaluation_id": None,
            "evaluation": None,
            "unevaluated_reason": reason,
        }

    if evaluation_row is None:
        raise ValueError("state")

    return {
        "test_run_id": str(test_run_id),
        "gate_evaluation_id": str(evaluation_row.id),
        "evaluation": serialize_detail(evaluation_row),
        "unevaluated_reason": None,
    }
