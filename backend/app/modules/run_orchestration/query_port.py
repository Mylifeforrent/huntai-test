"""Cross-module read-only queries for run_orchestration (no ORM export)."""

import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.models import TestRun

WAITING_STATUSES = frozenset({"WAITING_APPROVAL", "WAITING_EXTERNAL"})
DEFAULT_LIST_LIMIT = 50


class RunScope(TypedDict):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str


class RunClusteringContext(TypedDict):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    created_by: uuid.UUID | None
    result_summary: dict[str, Any] | None


class RunGateContext(TypedDict):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    execution_source: str
    result_summary: dict[str, Any] | None
    gate_evaluation_id: uuid.UUID | None


class TerminalRunGateContext(RunGateContext):
    updated_at: datetime


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _dwell_seconds(run: TestRun, *, now: datetime) -> int | None:
    if run.status not in WAITING_STATUSES:
        return None
    updated = run.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return max(0, int((now - updated).total_seconds()))


def _serialize_workbench_run(run: TestRun, *, now: datetime) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "status": run.status,
        "version": run.aggregate_version,
        "execution_source": run.execution_source,
    }
    dwell = _dwell_seconds(run, now=now)
    if dwell is not None:
        payload["dwell_seconds"] = dwell
    if run.last_heartbeat_at is not None and run.status not in WAITING_STATUSES:
        payload["last_heartbeat_at"] = _iso(run.last_heartbeat_at)
    return payload


class CommandReceiptPointer(TypedDict):
    id: uuid.UUID
    command_type: str
    status: str
    resource_type: str
    resource_id: uuid.UUID
    project_id: uuid.UUID
    created_by: uuid.UUID | None


async def get_command_receipt_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    receipt_id: uuid.UUID,
) -> CommandReceiptPointer | None:
    receipt = await repo.get_command_receipt(
        session,
        organization_id=organization_id,
        receipt_id=receipt_id,
    )
    if receipt is None:
        return None
    return {
        "id": receipt.id,
        "command_type": receipt.command_type,
        "status": receipt.status,
        "resource_type": receipt.resource_type,
        "resource_id": receipt.resource_id,
        "project_id": receipt.project_id,
        "created_by": receipt.created_by,
    }


class AgentRunPointer(TypedDict):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    execution_source: str


async def get_agent_run_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> AgentRunPointer | None:
    scope = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if scope is None:
        return None
    return {
        "id": scope.id,
        "project_id": scope.project_id,
        "status": scope.status,
        "execution_source": scope.execution_source,
    }


async def get_run_scope(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> RunScope | None:
    run = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return None
    return {"id": run.id, "project_id": run.project_id, "status": run.status}


async def get_run_clustering_context(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> RunClusteringContext | None:
    run = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return None
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "created_by": run.created_by,
        "result_summary": dict(run.result_summary) if run.result_summary else None,
    }


async def get_run_for_gate(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> RunGateContext | None:
    run = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return None
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status,
        "execution_source": run.execution_source,
        "result_summary": dict(run.result_summary) if run.result_summary else None,
        "gate_evaluation_id": run.gate_evaluation_id,
    }


async def list_run_ids_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[uuid.UUID]:
    return await repo.list_run_ids_for_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
    )


async def list_workbench_active_runs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    effective_limit = DEFAULT_LIST_LIMIT if limit is None else limit
    now = datetime.now(UTC)
    rows = await repo.list_non_terminal_runs_for_projects(
        session,
        organization_id=organization_id,
        project_ids=project_ids,
        limit=effective_limit,
    )
    return [_serialize_workbench_run(row, now=now) for row in rows]


async def list_recent_terminal_runs_for_projects(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    limit: int,
) -> list[TerminalRunGateContext]:
    rows = await repo.list_recent_terminal_runs_for_projects(
        session,
        organization_id=organization_id,
        project_ids=project_ids,
        limit=limit,
    )
    return [
        {
            "id": row.id,
            "project_id": row.project_id,
            "status": row.status,
            "execution_source": row.execution_source,
            "result_summary": dict(row.result_summary) if row.result_summary else None,
            "gate_evaluation_id": row.gate_evaluation_id,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


async def get_latest_run_for_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    plan_id: uuid.UUID,
) -> dict[str, Any] | None:
    return await repo.get_latest_run_for_plan(
        session,
        organization_id=organization_id,
        plan_id=plan_id,
    )
