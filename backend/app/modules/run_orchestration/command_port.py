"""Cross-module commands for run_orchestration (no ORM export to consumers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration import repository as repo


async def create_command_receipt_for_command(
    session: AsyncSession,
    *,
    receipt_id: uuid.UUID,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    command_type: str,
    status: str,
    resource_type: str,
    resource_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    """Persist a command receipt in the caller's transaction (cross-module entry)."""
    await repo.create_command_receipt(
        session,
        receipt_id=receipt_id,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        command_type=command_type,
        status=status,
        accepted_at=created_at,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
    )


async def update_command_receipt_status(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    receipt_id: uuid.UUID,
    status: str,
) -> None:
    updated = await repo.update_command_receipt_status(
        session,
        organization_id=organization_id,
        receipt_id=receipt_id,
        status=status,
    )
    if updated is None:
        raise ValueError("not_found")


async def merge_clustering_projection(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    clustering: dict[str, Any],
) -> None:
    """Merge clustering projection into TestRun.result_summary without touching snapshot."""
    run = await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        for_update=True,
    )
    if run is None:
        raise ValueError("not_found")
    summary = dict(run.result_summary or {})
    summary["clustering"] = clustering
    run.result_summary = summary
    await session.flush()


async def apply_ci_observation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_id: uuid.UUID,
    body: bytes,
    observation_id: uuid.UUID,
    request_hash: str,
) -> uuid.UUID | None:
    from app.modules.run_orchestration.external_ci_executor import (
        merge_result_summary,
        parse_ci_observation_payload,
    )

    parsed = parse_ci_observation_payload(body)
    if parsed is None:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=organization_id,
                actor_user_id=None,
                action="ci_observation.parse_failed",
                resource_type="connector",
                resource_id=connector_id,
                result="failed",
                request_hash=request_hash,
            ),
        )
        return None

    job_id = str(parsed["job_id"])
    build_number = parsed.get("build_number")
    run = await repo.find_external_ci_run_for_observation(
        session,
        organization_id=organization_id,
        job_id=job_id,
        build_number=build_number if isinstance(build_number, int) else None,
    )
    if run is None:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=organization_id,
                actor_user_id=None,
                action="ci_observation_unbound",
                resource_type="connector",
                resource_id=connector_id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        return None

    now = datetime.now(UTC)
    phase = parsed.get("phase")
    status = parsed.get("status")
    ci_patch: dict[str, Any] = {"observation_id": str(observation_id)}
    if isinstance(build_number, int):
        ci_patch["build_number"] = build_number

    if phase == "STARTED" and run.status == "WAITING_EXTERNAL":
        summary = merge_result_summary(
            run.result_summary if isinstance(run.result_summary, dict) else None,
            patch={"ci": ci_patch},
        )
        await repo.update_test_run_status(
            session,
            run=run,
            new_status="RUNNING",
            updated_at=now,
            result_summary=summary,
            heartbeat=True,
        )
        await session.flush()
        return None

    terminal_phases = {"COMPLETED", "FINALIZED"}
    terminal_statuses = {"SUCCESS", "FAILURE", "ABORTED", "UNSTABLE"}
    if phase in terminal_phases or status in terminal_statuses:
        summary = merge_result_summary(
            run.result_summary if isinstance(run.result_summary, dict) else None,
            patch={"ci": ci_patch},
        )
        run.result_summary = summary
        run.updated_at = now
        run.aggregate_version += 1
        await session.flush()
        return run.id

    summary = merge_result_summary(
        run.result_summary if isinstance(run.result_summary, dict) else None,
        patch={"ci": ci_patch},
    )
    run.result_summary = summary
    run.updated_at = now
    run.aggregate_version += 1
    await session.flush()
    return None


async def resume_ci_run_after_observation(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    from app.modules.run_orchestration.external_ci_executor import resume_external_ci_run

    await resume_external_ci_run(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )


async def cas_attach_gate_evaluation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    gate_evaluation_id: uuid.UUID,
) -> bool:
    return await repo.cas_attach_gate_evaluation(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        gate_evaluation_id=gate_evaluation_id,
    )


async def cancel_external_ci_with_collect(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    from app.modules.run_orchestration.external_ci_executor import best_effort_collect_on_cancel

    await best_effort_collect_on_cancel(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )


async def cas_resume_perf_after_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    approval_id: uuid.UUID,
    param_hash: str,
) -> str:
    """Resume a WAITING_APPROVAL perf run after perf_high_risk approval."""
    return await repo.resume_perf_after_approval(
        session,
        organization_id=organization_id,
        run_id=test_run_id,
        approval_id=approval_id,
        param_hash=param_hash,
    )


async def cas_cancel_perf_from_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> bool:
    """Cancel a perf run waiting for a perf_high_risk approval (reject/expire)."""
    return await repo.cancel_perf_from_approval(
        session,
        organization_id=organization_id,
        run_id=test_run_id,
    )
