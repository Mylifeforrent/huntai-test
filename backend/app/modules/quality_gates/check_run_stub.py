"""GitHub Check Run three-phase writeback stub (no real HTTP)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

MAX_SYNC_ATTEMPTS = 3


class CheckRunSyncError(Exception):
    """Raised when a stub phase update fails (for retry testing)."""


async def _apply_phase(
    ref: dict[str, Any],
    *,
    phase: str,
    conclusion: str | None,
    attempt: int,
) -> dict[str, Any]:
    phases = list(ref.get("phases") or [])
    if phase == "queued":
        phases = ["queued"]
        ref["sync_status"] = "queued"
    elif phase == "in_progress":
        phases = ["queued", "in_progress"]
        ref["sync_status"] = "in_progress"
    elif phase == "completed":
        phases = ["queued", "in_progress", "completed"]
        ref["sync_status"] = "completed"
        ref["conclusion"] = conclusion
    ref["phases"] = phases
    ref["attempts"] = attempt
    return ref


async def sync_check_run_stub(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    evaluation_result: str,
    check_run_ref: dict[str, Any] | None,
    request_hash: str,
    policy_mode: str = "blocking",
) -> dict[str, Any]:
    if evaluation_result == "pass":
        conclusion = "success"
    else:
        # report_only records the fail but must not block CI (M2: 仅报告 ⇄ 阻断).
        conclusion = "failure" if policy_mode == "blocking" else "neutral"
    ref: dict[str, Any] = dict(check_run_ref or {})
    ref["external_id"] = str(evaluation_id)

    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        try:
            ref = await _apply_phase(ref, phase="queued", conclusion=None, attempt=attempt)
            ref = await _apply_phase(ref, phase="in_progress", conclusion=None, attempt=attempt)
            ref = await _apply_phase(ref, phase="completed", conclusion=conclusion, attempt=attempt)
            return ref
        except CheckRunSyncError:
            if attempt >= MAX_SYNC_ATTEMPTS:
                break
            continue

    ref["sync_status"] = "failed"
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=None,
            action="check_run.sync_failed",
            resource_type="gate_evaluation",
            resource_id=evaluation_id,
            result="failed",
            request_hash=request_hash,
        ),
    )
    return ref
