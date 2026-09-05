"""Agent trajectory read model (API-067, FR-19 M2 pilot).

The A8 trajectory is stored as an Artifact (kind=agent_trajectory) written by
the agent worker. This service projects it sanitized: tool args appear only as
hashes, no parameter originals, no secrets.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import object_store
from app.modules.results_evidence import repository as repo
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
TRAJECTORY_ARTIFACT_KIND = "agent_trajectory"


def _empty_trajectory(test_run_id: uuid.UUID, reason: str | None) -> dict[str, Any]:
    return {
        "test_run_id": str(test_run_id),
        "available": False,
        "unavailable_reason": reason,
        "a8": None,
        "policy_denials": [],
    }


async def get_trajectory_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
) -> dict[str, Any]:
    organization_id = ctx.organization.id
    pointer = await run_query.get_agent_run_pointer(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if pointer is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=organization_id,
        project_id=pointer["project_id"],
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    if pointer["execution_source"] != "agent":
        return _empty_trajectory(test_run_id, "not_agent_source")

    artifact = await repo.get_artifact_by_run_kind(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        kind=TRAJECTORY_ARTIFACT_KIND,
    )
    if artifact is None or not object_store.file_exists(artifact.object_key):
        return _empty_trajectory(test_run_id, "trajectory_not_available")

    raw = object_store.read_bytes(artifact.object_key)
    try:
        stored = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("not_found") from exc
    if not isinstance(stored, dict):
        raise ValueError("not_found")

    raw_meta = stored.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    steps: list[dict[str, Any]] = []
    raw_steps_obj = stored.get("steps")
    raw_steps: list[Any] = raw_steps_obj if isinstance(raw_steps_obj, list) else []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        raw_action = step.get("action")
        action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
        steps.append(
            {
                "seq": step.get("seq"),
                "intent": step.get("intent"),
                "action": {
                    "tool": action.get("tool"),
                    "args_hash": action.get("args_hash"),
                },
                "observation_ref": step.get("observation_ref"),
                "screenshot_ref": step.get("screenshot_ref"),
                "elapsed_ms": step.get("elapsed_ms"),
            }
        )
    a8 = {
        "task_id": stored.get("task_id"),
        "status": stored.get("status"),
        "steps": steps,
        "assertion_results": stored.get("assertion_results", []),
        "token_usage": stored.get("token_usage", {}),
        "incomplete": stored.get("incomplete", True),
    }
    return {
        "test_run_id": str(test_run_id),
        "available": True,
        "unavailable_reason": None,
        "a8": a8,
        "policy_denials": meta.get("policy_denials", []),
    }
