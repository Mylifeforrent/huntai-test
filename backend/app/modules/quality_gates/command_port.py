"""Cross-module commands for quality_gates (no ORM export to consumers)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.check_run_stub import sync_check_run_stub
from app.modules.quality_gates.evaluation_rules import (
    SKIP_STATUSES,
    TERMINAL_STATUSES,
    VALID_INSERT_RESULTS,
    build_threshold_details,
    compute_pass_rate,
    is_partial_report,
)
from app.modules.quality_gates.models import GateEvaluation
from app.modules.quality_gates.service import serialize_detail as serialize_policy_detail
from app.modules.results_evidence import query_port as evidence_query
from app.modules.run_orchestration import query_port as run_query


async def _evaluate_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> str | None:
    run = await run_query.get_run_for_gate(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return None
    if run["gate_evaluation_id"] is not None:
        return None
    if run["execution_source"] == "agent":
        return "agent_source"
    if run["status"] in SKIP_STATUSES:
        return "cancelled_or_timeout"
    if run["status"] not in TERMINAL_STATUSES:
        return None

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
        test_run_id=test_run_id,
    )
    summary = run["result_summary"] if isinstance(run["result_summary"], dict) else None
    if is_partial_report(result_summary=summary, case_results=case_results):
        return "partial_report"

    pass_rate, pass_detail = compute_pass_rate(case_results)
    threshold_details, result = build_threshold_details(
        thresholds=policy.thresholds,
        pass_rate=pass_rate,
        pass_detail=pass_detail,
    )
    if result not in VALID_INSERT_RESULTS:
        return "policy_unmet"

    now = datetime.now(UTC)
    evaluation_id = uuid.uuid4()
    request_hash = hashlib.sha256(f"{test_run_id}:{policy.id}:{result}".encode()).hexdigest()
    check_run_ref = await sync_check_run_stub(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
        evaluation_result=result,
        check_run_ref=None,
        request_hash=request_hash,
        policy_mode=policy.mode,
    )
    row = GateEvaluation(
        id=evaluation_id,
        organization_id=organization_id,
        created_at=now,
        created_by=None,
        test_run_id=test_run_id,
        policy_id=policy.id,
        policy_snapshot=serialize_policy_detail(policy),
        result=result,
        threshold_details=threshold_details,
        check_run_ref=check_run_ref,
        waiver_approval_id=None,
        evidence_refs=[],
    )
    await repo.insert_gate_evaluation(session, row)

    from app.modules.run_orchestration import command_port as run_command

    attached = await run_command.cas_attach_gate_evaluation(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        gate_evaluation_id=evaluation_id,
    )
    if not attached:
        await repo.delete_gate_evaluation(
            session,
            organization_id=organization_id,
            evaluation_id=evaluation_id,
        )
        return None
    return None


async def schedule_gate_evaluation(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await _evaluate_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        await session.commit()


async def attach_waiver(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    approval_id: uuid.UUID,
) -> bool:
    return await repo.cas_attach_waiver(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
        waiver_approval_id=approval_id,
    )


__all__ = ["attach_waiver", "schedule_gate_evaluation"]
