"""Shared unevaluated-reason projection for API-146 and workbench anomalies."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.evaluation_rules import (
    SKIP_STATUSES,
    TERMINAL_STATUSES,
    is_partial_report,
)
from app.modules.results_evidence import query_port as evidence_query
from app.modules.run_orchestration.query_port import RunGateContext


async def unevaluated_reason_for_run(
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
    perf_raw = summary.get("perf") if isinstance(summary, dict) else None
    perf_run = (
        isinstance(summary, dict)
        and summary.get("execution_source") == "perf"
        or isinstance(perf_raw, dict)
    )
    if perf_run and not (
        isinstance(perf_raw, dict)
        and (
            isinstance(perf_raw.get("p95_ms"), (int, float))
            or isinstance(perf_raw.get("error_rate"), (int, float))
        )
    ):
        return "perf_report_missing"
    return "not_terminal"
