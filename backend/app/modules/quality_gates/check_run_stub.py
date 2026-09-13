"""GitHub Check Run three-phase writeback stub (in-process or loopback mock HTTP)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub.query_port import get_loopback_outbound_target
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


def _github_owner_repo(action_contract: dict[str, Any]) -> tuple[str, str]:
    owner = action_contract.get("owner")
    repo = action_contract.get("repo")
    if not isinstance(owner, str) or not owner.strip():
        owner = "local-dev"
    if not isinstance(repo, str) or not repo.strip():
        repo = "demo"
    return owner.strip(), repo.strip()


async def _sync_check_run_loopback(
    target: dict[str, Any],
    *,
    conclusion: str,
    evaluation_id: uuid.UUID,
    attempt: int,
) -> dict[str, Any]:
    contract = target.get("action_contract")
    action_contract = contract if isinstance(contract, dict) else {}
    owner, repo = _github_owner_repo(action_contract)
    base_url = str(target["base_url"]).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            create_resp = await client.post(
                f"{base_url}/repos/{owner}/{repo}/check-runs",
                json={"name": f"HuntAI Gate {evaluation_id}", "head_sha": "local"},
            )
            if create_resp.status_code != 201:
                raise CheckRunSyncError("check run create failed")
            try:
                created = create_resp.json()
            except ValueError as exc:
                raise CheckRunSyncError("check run create invalid response") from exc
            if not isinstance(created, dict) or "id" not in created:
                raise CheckRunSyncError("check run create invalid response")
            check_id = created["id"]
            in_progress_resp = await client.patch(
                f"{base_url}/repos/{owner}/{repo}/check-runs/{check_id}",
                json={"status": "in_progress"},
            )
            if in_progress_resp.status_code != 200:
                raise CheckRunSyncError("check run in_progress failed")
            completed_resp = await client.patch(
                f"{base_url}/repos/{owner}/{repo}/check-runs/{check_id}",
                json={"status": "completed", "conclusion": conclusion},
            )
            if completed_resp.status_code != 200:
                raise CheckRunSyncError("check run completed failed")
    except httpx.HTTPError as exc:
        raise CheckRunSyncError(str(exc)) from exc
    html_url = created.get("html_url") if isinstance(created.get("html_url"), str) else None
    return {
        "phases": ["queued", "in_progress", "completed"],
        "sync_status": "completed",
        "conclusion": conclusion,
        "external_check_id": check_id,
        "html_url": html_url,
        "attempts": attempt,
    }


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
    loopback_target = await get_loopback_outbound_target(
        session,
        organization_id=organization_id,
        connector_type="github",
    )

    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        try:
            if loopback_target is None:
                ref = await _apply_phase(ref, phase="queued", conclusion=None, attempt=attempt)
                ref = await _apply_phase(ref, phase="in_progress", conclusion=None, attempt=attempt)
                ref = await _apply_phase(
                    ref, phase="completed", conclusion=conclusion, attempt=attempt
                )
            else:
                ref = await _sync_check_run_loopback(
                    loopback_target,
                    conclusion=conclusion,
                    evaluation_id=evaluation_id,
                    attempt=attempt,
                )
                ref["external_id"] = str(evaluation_id)
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
