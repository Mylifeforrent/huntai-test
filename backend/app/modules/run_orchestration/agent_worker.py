"""Agent subprocess worker for agent-mode runs (S-M2-07, FR-19 M2 pilot).

Executes agent-mode cases step by step through the Tool Router
(whitelist → Policy Gate), records an A8 trajectory (Artifact + CaseResult),
honors the persisted stop signal (API-063) and manifest limits
(max_steps / total timeout). No auto-retry; over-limit exits are incomplete
and finalize the run via STOPPING → CANCELLED (AC-083).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.core.db import get_session_factory
from app.modules.approval_policy.policy_gate import PolicyGate, evaluate_policy_gate
from app.modules.results_evidence import object_store
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.command_port import (
    ArtifactWrite,
    CaseResultWrite,
    StepRunWrite,
    append_artifact,
    append_case_result,
    append_step_run,
)
from app.modules.run_orchestration import repository as run_repo
from app.modules.run_orchestration.http_runner import evaluate_assertion, execute_request_step
from app.modules.run_orchestration.variable_resolver import validate_and_resolve_snapshot

TRAJECTORY_ARTIFACT_KIND = "agent_trajectory"
MAX_CONSECUTIVE_DENIES = 3


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _args_hash(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _step_tool(step: dict[str, Any]) -> str:
    return str(step.get("action", ""))


def _step_declared_level(step: dict[str, Any]) -> str | None:
    params = step.get("params")
    if not isinstance(params, dict):
        return None
    level = params.get("side_effect_level")
    return str(level) if isinstance(level, str) else None


def _args_hash_of(step: dict[str, Any]) -> str | None:
    params = step.get("params")
    if not isinstance(params, dict):
        return None
    return _args_hash(params)


def _intent(step: dict[str, Any], seq: int) -> str:
    params = step.get("params")
    if isinstance(params, dict) and isinstance(params.get("intent"), str):
        return str(params["intent"])
    return f"step {seq}: {_step_tool(step)}"


class _RunLimit(Exception):
    """Raised when the run must terminate without completing all steps."""


async def _stop_requested(
    session: Any, *, organization_id: uuid.UUID, test_run_id: uuid.UUID
) -> bool:
    run = await run_repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return True
    return run.status == "STOPPING" or run.stop_signal_at is not None


def _validate_agent_manifest(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    tools_raw = raw.get("allowed_tools")
    if not isinstance(tools_raw, list) or not tools_raw:
        return None
    allowed_tools = [str(tool) for tool in tools_raw]
    max_steps = raw.get("max_steps")
    total_timeout = raw.get("total_timeout_seconds")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        return None
    if (
        not isinstance(total_timeout, (int, float))
        or isinstance(total_timeout, bool)
        or total_timeout < 1
    ):
        return None
    return {
        "allowed_tools": allowed_tools,
        "max_steps": max_steps,
        "total_timeout_seconds": total_timeout,
    }


async def run_agent_worker(payload: dict[str, Any]) -> None:
    organization_id = uuid.UUID(str(payload["organization_id"]))
    test_run_id = uuid.UUID(str(payload["test_run_id"]))
    created_by_raw = payload.get("created_by")
    created_by = uuid.UUID(str(created_by_raw)) if created_by_raw else None
    cases: list[dict[str, Any]] = [
        case for case in payload.get("cases", []) if isinstance(case, dict)
    ]
    params = payload.get("params") or {}
    manifest = _validate_agent_manifest(payload.get("manifest"))
    base_url = str(payload.get("base_url", "")).strip()

    factory = get_session_factory()
    started_at = datetime.now(UTC)
    timeout_seconds = float(manifest["total_timeout_seconds"]) if manifest else 0.0
    deadline = started_at + timedelta(seconds=timeout_seconds) if timeout_seconds > 0 else None
    max_steps = int(manifest["max_steps"]) if manifest else 0
    allowed_tools = set(manifest["allowed_tools"]) if manifest else set()

    policy_denials: list[str] = []
    a8_steps: list[dict[str, Any]] = []
    executed_steps: list[dict[str, Any]] = []
    resolved_assertions_all: list[dict[str, Any]] = []
    consecutive_denies = 0
    seq_cursor = 0
    a8_status = "incomplete"
    run_outcome = "CANCELLED"
    failure_reason: str | None = None
    case_results: list[dict[str, Any]] = []
    all_assertion_results: list[dict[str, Any]] = []

    try:
        if manifest is None:
            failure_reason = "invalid_agent_manifest"
            raise _RunLimit()
        if not base_url:
            failure_reason = "missing_target_env"
            raise _RunLimit()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for case in cases:
                resolved_steps, resolved_assertions, errors = validate_and_resolve_snapshot(
                    params=params,
                    steps=case.get("steps", []),
                    assertions=case.get("assertions", []),
                )
                if errors:
                    failure_reason = "variable_unresolved"
                    raise _RunLimit()

                case_step_count = 0
                last_observation: dict[str, Any] | None = None
                case_assertion_results: list[dict[str, Any]] = []
                case_completed = True
                for step in resolved_steps:
                    seq_cursor += 1
                    async with factory() as session:
                        if await _stop_requested(
                            session, organization_id=organization_id, test_run_id=test_run_id
                        ):
                            await session.commit()
                            a8_status = "terminated"
                            run_outcome = "CANCELLED"
                            case_completed = False
                            break
                        await session.commit()

                    if deadline is not None and datetime.now(UTC) >= deadline:
                        a8_status = "incomplete"
                        run_outcome = "CANCELLED"
                        case_completed = False
                        failure_reason = "total_timeout"
                        break
                    if seq_cursor > max_steps:
                        a8_status = "incomplete"
                        run_outcome = "CANCELLED"
                        case_completed = False
                        failure_reason = "max_steps_reached"
                        break

                    tool = _step_tool(step)
                    observation: dict[str, Any] | None = None
                    deny_reason: str | None = None
                    if tool not in allowed_tools:
                        deny_reason = "tool_not_allowlisted"
                    else:
                        gate = evaluate_policy_gate(
                            action_type="agent_tool_action",
                            payload={"declared_side_effect_level": _step_declared_level(step)},
                            reauth_required=False,
                        )
                        if gate.gate is PolicyGate.ALLOW:
                            try:
                                observation = await execute_request_step(
                                    client, base_url=base_url, step=step
                                )
                            except httpx.HTTPError, OSError:
                                observation = {
                                    "ok": False,
                                    "error": "request_failed",
                                    "elapsed_ms": 0,
                                }
                        elif gate.gate is PolicyGate.DENY:
                            deny_reason = f"policy_deny:{gate.deny_reason}"
                        else:
                            deny_reason = f"policy_block:{str(gate.gate.value).lower()}"

                    if deny_reason is not None:
                        consecutive_denies += 1
                        policy_denials.append(f"step_{seq_cursor}:{deny_reason}")
                        async with factory() as audit_session:
                            await append_audit_event(
                                audit_session,
                                AuditAppendInput(
                                    organization_id=organization_id,
                                    actor_user_id=created_by,
                                    action="agent_tool.deny",
                                    resource_type="TestRun",
                                    resource_id=test_run_id,
                                    result="denied",
                                    request_hash=f"{test_run_id}:{seq_cursor}",
                                ),
                            )
                            await audit_session.commit()
                        if consecutive_denies >= MAX_CONSECUTIVE_DENIES:
                            a8_status = "incomplete"
                            run_outcome = "CANCELLED"
                            case_completed = False
                            failure_reason = "consecutive_policy_denies"
                            break
                        case_step_count += 1
                        a8_steps.append(
                            {
                                "seq": seq_cursor,
                                "intent": _intent(step, seq_cursor),
                                "action": {"tool": tool, "args_hash": None},
                                "observation_ref": None,
                                "screenshot_ref": None,
                                "elapsed_ms": 0,
                                "denied": True,
                                "deny_reason": deny_reason,
                            }
                        )
                        continue

                    case_step_count += 1
                    consecutive_denies = 0
                    executed_steps.append({"seq": seq_cursor, "tool": tool, "action": step})
                    if observation is not None:
                        last_observation = observation
                        elapsed_ms = int(observation.get("elapsed_ms") or 0)
                    else:
                        elapsed_ms = 0
                    a8_steps.append(
                        {
                            "seq": seq_cursor,
                            "intent": _intent(step, seq_cursor),
                            "action": {
                                "tool": tool,
                                "args_hash": _args_hash_of(step),
                            },
                            "observation_ref": None,
                            "screenshot_ref": None,
                            "elapsed_ms": elapsed_ms,
                            "denied": False,
                        }
                    )

                    async with factory() as session:
                        run = await run_repo.get_test_run(
                            session,
                            organization_id=organization_id,
                            test_run_id=test_run_id,
                            for_update=True,
                        )
                        if run is not None and run.status == "RUNNING":
                            await run_repo.update_test_run_status(
                                session,
                                run=run,
                                new_status="RUNNING",
                                updated_at=datetime.now(UTC),
                                heartbeat=True,
                            )
                        await session.commit()
                else:
                    if last_observation is None and resolved_steps:
                        case_completed = False
                    else:
                        for assertion in resolved_assertions:
                            if not isinstance(assertion, dict):
                                case_assertion_results.append(
                                    {"passed": False, "error": "invalid_assertion"}
                                )
                                continue
                            case_assertion_results.append(
                                evaluate_assertion(assertion, last_observation or {})
                            )

                case_outcome = (
                    "passed"
                    if case_completed
                    and case_assertion_results
                    and all(item.get("passed", False) for item in case_assertion_results)
                    else "failed"
                )
                case_results.append(
                    {
                        "case": case,
                        "outcome": case_outcome,
                        "is_partial": not case_completed,
                        "step_count": case_step_count,
                    }
                )
                all_assertion_results.extend(case_assertion_results)
                if case_completed:
                    resolved_assertions_all.extend(
                        item for item in resolved_assertions if isinstance(item, dict)
                    )
                if not case_completed:
                    break

        if a8_status == "incomplete" and run_outcome == "CANCELLED" and failure_reason is None:
            # The loop finished normally: assertion results decide the outcome.
            a8_status = "completed"
            all_passed = bool(case_results) and all(
                item["outcome"] == "passed" for item in case_results
            )
            run_outcome = "SUCCEEDED" if all_passed else "FAILED"
    except _RunLimit:
        a8_status = "incomplete"
        run_outcome = "CANCELLED"

    now = datetime.now(UTC)
    incomplete = a8_status != "completed"
    trajectory: dict[str, Any] = {
        "task_id": str(test_run_id),
        "status": a8_status,
        "steps": a8_steps,
        "assertion_results": all_assertion_results,
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0},
        "incomplete": incomplete,
        "executed_steps": executed_steps,
        "meta": {
            "organization_id": str(organization_id),
            "finished_at": _iso(now),
            "failure_reason": failure_reason,
            "policy_denials": policy_denials,
            "assertions": resolved_assertions_all,
        },
    }

    async with factory() as session:
        run = await run_repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is None:
            await session.commit()
            return
        now = datetime.now(UTC)
        if run.status == "STOPPING" or run.stop_signal_at is not None:
            run_outcome = "CANCELLED"
            trajectory["status"] = "terminated"
            trajectory["incomplete"] = True
        for case_result_item in case_results:
            case = case_result_item["case"]
            case_id = uuid.UUID(str(case["id"]))
            version_raw = case.get("version_id")
            version_id = uuid.UUID(str(version_raw)) if version_raw else None
            case_result_id = await append_case_result(
                session,
                organization_id=organization_id,
                created_by=created_by,
                created_at=now,
                payload=CaseResultWrite(
                    test_run_id=test_run_id,
                    test_case_id=case_id,
                    test_case_version_id=version_id,
                    attempt_seq=1,
                    outcome=case_result_item["outcome"],
                    is_partial=case_result_item["is_partial"],
                    normalized_summary={
                        "execution_source": "agent",
                        "a8_status": trajectory["status"],
                        "failure_reason": failure_reason,
                    },
                ),
            )
            case_step_slice = _steps_for_case(a8_steps, case_result_item, case_results)
            for record_index, a8_step in enumerate(case_step_slice):
                await append_step_run(
                    session,
                    organization_id=organization_id,
                    created_by=created_by,
                    created_at=now,
                    payload=StepRunWrite(
                        case_result_id=case_result_id,
                        step_index=record_index,
                        action={
                            "tool": a8_step["action"]["tool"],
                            "args_hash": a8_step["action"]["args_hash"],
                            "intent": a8_step["intent"],
                        },
                        assertion_results=None,
                        is_incomplete=bool(a8_step.get("denied")) or incomplete,
                        observation_ref=None,
                        token_usage={"prompt_tokens": 0, "completion_tokens": 0},
                    ),
                )
        artifact_id = uuid.uuid4()
        object_key = object_store.generate_object_key(
            organization_id=organization_id,
            artifact_id=artifact_id,
            filename="trajectory.json",
        )
        trajectory_bytes = json.dumps(trajectory, ensure_ascii=False, indent=2).encode("utf-8")
        checksum = object_store.write_bytes(object_key=object_key, data=trajectory_bytes)
        await append_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            payload=ArtifactWrite(
                test_run_id=test_run_id,
                kind=TRAJECTORY_ARTIFACT_KIND,
                object_key=object_key,
                checksum=checksum,
                case_result_id=None,
                byte_size=len(trajectory_bytes),
                mime_type="application/json",
                data_classification="Internal",
                original_filename="trajectory.json",
                artifact_id=artifact_id,
            ),
        )
        if run.status == "RUNNING":
            if run_outcome in {"SUCCEEDED", "FAILED"}:
                await run_repo.update_test_run_status(
                    session,
                    run=run,
                    new_status=run_outcome,
                    updated_at=now,
                    result_summary={
                        "cases": len(case_results),
                        "outcome": run_outcome.lower(),
                        "agent": {"a8_status": trajectory["status"]},
                        "clustering": {
                            "generation_status": "pending",
                            "degraded": False,
                            "unclustered_refs": [],
                        },
                    },
                )
            else:
                # System-initiated termination: STOPPING → CANCELLED (AC-083).
                await run_repo.update_test_run_status(
                    session,
                    run=run,
                    new_status="STOPPING",
                    updated_at=now,
                )
                await session.commit()
                await run_repo.update_test_run_status(
                    session,
                    run=run,
                    new_status="CANCELLED",
                    updated_at=datetime.now(UTC),
                )
        elif run.status == "STOPPING":
            await run_repo.update_test_run_status(
                session,
                run=run,
                new_status="CANCELLED",
                updated_at=now,
            )
        await session.commit()


def _steps_for_case(
    a8_steps: list[dict[str, Any]],
    case_result_item: dict[str, Any],
    case_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Slice the run-level step list back to one case's executed steps."""
    start = 0
    for prior in case_results:
        if prior is case_result_item:
            break
        start += int(prior["step_count"])
    count = int(case_result_item["step_count"])
    return a8_steps[start : start + count]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent mode worker (FR-19 M2 pilot)")
    parser.add_argument("payload_path", type=str, help="JSON payload file path")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.payload_path).read_text(encoding="utf-8"))
    asyncio.run(run_agent_worker(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
