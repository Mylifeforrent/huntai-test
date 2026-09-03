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
