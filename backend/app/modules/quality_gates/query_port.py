"""Cross-module read-only queries for quality_gates (no ORM export to consumers)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.evaluation_service import serialize_detail
from app.modules.quality_gates.models import GateEvaluation
from app.modules.quality_gates.service import serialize_detail as serialize_policy_detail
from app.modules.quality_gates.unevaluated_reason import unevaluated_reason_for_run
from app.modules.run_orchestration import query_port as run_query

WORKBENCH_UNEVALUATED_INCLUDE = frozenset({"policy_unmet", "partial_report", "perf_report_missing"})


def _serialize_workbench_evaluation_anomaly(row: GateEvaluation) -> dict[str, Any]:
    ref = row.check_run_ref if isinstance(row.check_run_ref, dict) else {}
    kind = "check_run_failed" if ref.get("sync_status") == "failed" else "fail_evaluation"
    return {
        "kind": kind,
        "test_run_id": str(row.test_run_id),
        "gate_evaluation_id": str(row.id),
        "result": row.result,
        "unevaluated_reason": None,
    }


async def list_workbench_gate_anomalies(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    limit: int,
) -> list[dict[str, Any]]:
    if not project_ids:
        return []

    run_ids: list[uuid.UUID] = []
    for project_id in project_ids:
        run_ids.extend(
            await run_query.list_run_ids_for_project(
                session,
                organization_id=organization_id,
                project_id=project_id,
            )
        )
    if not run_ids:
        return []

    deduped_run_ids = list(dict.fromkeys(run_ids))
    evaluation_rows = await repo.list_workbench_anomaly_evaluations(
        session,
        organization_id=organization_id,
        test_run_ids=deduped_run_ids,
        limit=limit,
    )
    evaluated_run_ids = await repo.list_evaluated_test_run_ids(
        session,
        organization_id=organization_id,
        test_run_ids=deduped_run_ids,
    )
    terminal_runs = await run_query.list_recent_terminal_runs_for_projects(
        session,
        organization_id=organization_id,
        project_ids=project_ids,
        limit=limit,
    )

    merged: list[tuple[datetime, uuid.UUID, dict[str, Any]]] = []
    for row in evaluation_rows:
        merged.append(
            (
                row.created_at,
                row.id,
                _serialize_workbench_evaluation_anomaly(row),
            )
        )

    for run in terminal_runs:
        if run["id"] in evaluated_run_ids:
            continue
        reason = await unevaluated_reason_for_run(
            session,
            organization_id=organization_id,
            run=run,
        )
        if reason not in WORKBENCH_UNEVALUATED_INCLUDE:
            continue
        merged.append(
            (
                run["updated_at"],
                run["id"],
                {
                    "kind": "unevaluated",
                    "test_run_id": str(run["id"]),
                    "gate_evaluation_id": None,
                    "result": None,
                    "unevaluated_reason": reason,
                },
            )
        )

    merged.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in merged[:limit]]


async def get_latest_gate_evaluation_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    from app.modules.run_orchestration import query_port as run_query

    run_ids = await run_query.list_run_ids_for_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
    )
    if not run_ids:
        return None
    rows = await repo.list_gate_evaluations(
        session,
        organization_id=organization_id,
        test_run_ids=run_ids,
        test_run_id=None,
        result_filter=None,
        created_from=None,
        created_to=None,
        cursor_created_at=None,
        cursor_id=None,
        limit=1,
    )
    if not rows:
        return None
    latest = rows[0]
    return {"id": latest.id, "result": latest.result, "test_run_id": latest.test_run_id}


async def get_policy_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_policy_for_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
    )
    if row is None:
        return None
    return serialize_policy_detail(row)


async def get_evaluation_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_gate_evaluation(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
    )
    if row is None:
        return None
    run = await run_query.get_run_for_gate(
        session,
        organization_id=organization_id,
        test_run_id=row.test_run_id,
    )
    payload = serialize_detail(row)
    if run is not None:
        payload["project_id"] = str(run["project_id"])
    return payload


async def get_evaluation_for_test_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_gate_evaluation_for_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if row is None:
        return None
    run = await run_query.get_run_for_gate(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    payload = serialize_detail(row)
    if run is not None:
        payload["project_id"] = str(run["project_id"])
    return payload
