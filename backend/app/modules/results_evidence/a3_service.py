"""A3 locator heal suggestions — invoke, parse, merge into cluster fixes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.test_assets import query_port as test_assets_query
from app.modules.test_assets.locator_health import (
    WEB_LOCATOR_ACTIONS,
    extract_locator_health_from_steps,
    stable_locator_id,
)

PROMPT_VERSION = "prompt/locator-heal@1.0.0"
ACTION_LIKE_TOKENS = frozenset(
    {"click", "fill", "goto", "type", "select", "check", "hover", "expect"}
)
MAX_HINT_CHARS = 500


def _extract_structured_output(usage: dict[str, Any]) -> dict[str, Any] | None:
    raw = usage.get("structured_output")
    if isinstance(raw, dict):
        return raw
    return None


def _truncate_text(value: str, limit: int = MAX_HINT_CHARS) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _looks_like_action_expression(expression: str) -> bool:
    lowered = expression.strip().lower()
    if not lowered:
        return True
    if lowered in ACTION_LIKE_TOKENS:
        return True
    return lowered.startswith("action:") or lowered.startswith("javascript:")


def _validate_candidates(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        expression = item.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            continue
        if _looks_like_action_expression(expression):
            continue
        strategy = item.get("strategy")
        strategy_text = str(strategy) if isinstance(strategy, str) and strategy.strip() else "css"
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):  # fmt: skip
            confidence = 0.0
        candidates.append(
            {
                "strategy": strategy_text,
                "expression": expression.strip(),
                "reason": str(item.get("reason", "")),
                "confidence": confidence,
            }
        )
    return candidates


def _build_locator_health_patch(
    current: list[dict[str, Any]],
    locator_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    candidate_strategy = str(candidate.get("strategy", "css"))
    candidate_expr = str(candidate.get("expression", ""))
    candidate_id = stable_locator_id(candidate_strategy, candidate_expr)
    updated: list[dict[str, Any]] = []
    for loc in current:
        entry = dict(loc)
        if str(entry.get("locator_id", "")) == locator_id:
            entry["is_primary"] = False
        updated.append(entry)
    promoted = False
    for entry in updated:
        if str(entry.get("locator_id", "")) == candidate_id:
            entry["is_primary"] = True
            entry["expression"] = candidate_expr
            entry["strategy"] = candidate_strategy
            entry["health"] = "unknown"
            promoted = True
            break
    if not promoted:
        updated.append(
            {
                "locator_id": candidate_id,
                "strategy": candidate_strategy,
                "expression": candidate_expr,
                "is_primary": True,
                "health": "unknown",
            }
        )
    return {"locator_health": updated}


def _failed_selector_from_payload(payload: dict[str, Any]) -> str | None:
    for step in payload.get("step_assertions", []):
        if not isinstance(step, dict):
            continue
        action_obj = step.get("action")
        if not isinstance(action_obj, dict):
            continue
        action_name = str(action_obj.get("action", ""))
        if action_name not in WEB_LOCATOR_ACTIONS:
            continue
        params = action_obj.get("params")
        if isinstance(params, dict) and isinstance(params.get("selector"), str):
            return str(params["selector"])
    return None


def _locator_entry_for_id(
    locators: list[dict[str, Any]],
    locator_id: str,
) -> dict[str, Any] | None:
    for item in locators:
        if str(item.get("locator_id", "")) == locator_id:
            return item
    return None


def _fixes_from_a3_output(
    *,
    locator_id: str,
    current_locators: list[dict[str, Any]],
    structured: dict[str, Any],
    degraded: bool,
) -> list[dict[str, Any]]:
    candidates = _validate_candidates(structured.get("candidates"))
    semantic_note = structured.get("semantic_invariant_note")
    semantic_text = str(semantic_note) if semantic_note is not None else ""
    human_hint = structured.get("human_repair_hint")
    dom_diff = structured.get("dom_diff")
    fixes: list[dict[str, Any]] = []
    current_entry = _locator_entry_for_id(current_locators, locator_id)
    current_expr = str(current_entry.get("expression", "")) if current_entry else ""

    if degraded:
        degraded_fix: dict[str, Any] = {
            "field": "locator_health",
            "current": current_expr,
            "suggested": json.dumps({"locator_health": current_locators}, separators=(",", ":")),
            "reason": "A3 degraded — manual repair required",
            "confidence": 0.0,
            "locator_id": locator_id,
            "strategy": str(current_entry.get("strategy", "css")) if current_entry else "css",
            "can_auto_apply": False,
        }
        if semantic_text:
            degraded_fix["semantic_invariant_note"] = _truncate_text(semantic_text)
        if isinstance(human_hint, str) and human_hint.strip():
            degraded_fix["human_repair_hint"] = _truncate_text(human_hint)
        if isinstance(dom_diff, str) and dom_diff.strip():
            degraded_fix["dom_diff"] = _truncate_text(dom_diff)
        if not isinstance(degraded_fix.get("human_repair_hint"), str):
            degraded_fix["human_repair_hint"] = _truncate_text(
                "A3 degraded; inspect DOM and update locator manually"
            )
        fixes.append(degraded_fix)
        return fixes

    for candidate in candidates:
        if candidate["confidence"] >= 0.7:
            patch = _build_locator_health_patch(current_locators, locator_id, candidate)
            fixes.append(
                {
                    "field": "locator_health",
                    "current": current_expr,
                    "suggested": json.dumps(patch, separators=(",", ":")),
                    "reason": candidate.get("reason", ""),
                    "confidence": candidate["confidence"],
                    "locator_id": locator_id,
                    "strategy": candidate["strategy"],
                    "can_auto_apply": False,
                    "candidates": candidates,
                    "semantic_invariant_note": (
                        _truncate_text(semantic_text) if semantic_text else None
                    ),
                }
            )
            break
    else:
        low_conf_fix: dict[str, Any] = {
            "field": "locator_health",
            "current": current_expr,
            "suggested": json.dumps({"locator_health": current_locators}, separators=(",", ":")),
            "reason": "No high-confidence locator candidates",
            "confidence": 0.0,
            "locator_id": locator_id,
            "strategy": str(current_entry.get("strategy", "css")) if current_entry else "css",
            "can_auto_apply": False,
            "candidates": candidates,
        }
        if semantic_text:
            low_conf_fix["semantic_invariant_note"] = _truncate_text(semantic_text)
        if isinstance(human_hint, str) and human_hint.strip():
            low_conf_fix["human_repair_hint"] = _truncate_text(human_hint)
        if isinstance(dom_diff, str) and dom_diff.strip():
            low_conf_fix["dom_diff"] = _truncate_text(dom_diff)
        fixes.append(low_conf_fix)
    return fixes


async def run_a3_for_locator_cluster(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    failure_refs: list[uuid.UUID],
    failed_payloads: dict[uuid.UUID, dict[str, Any]],
    case_result_test_case_ids: dict[uuid.UUID, uuid.UUID],
) -> list[dict[str, Any]]:
    if not failure_refs:
        return []
    case_result_id = failure_refs[0]
    payload = failed_payloads.get(case_result_id)
    test_case_id = case_result_test_case_ids.get(case_result_id)
    if payload is None or test_case_id is None:
        return []

    snapshot = await test_assets_query.get_test_case_snapshot(
        session,
        organization_id=organization_id,
        test_case_id=test_case_id,
    )
    if snapshot is None:
        return []

    steps = snapshot.get("steps", [])
    current_locators = list(snapshot.get("locator_health", []))
    if not current_locators and isinstance(steps, list):
        current_locators = extract_locator_health_from_steps(steps)

    failed_selector = _failed_selector_from_payload(payload)
    locator_id = None
    if failed_selector:
        locator_id = stable_locator_id("css", failed_selector)
    elif current_locators:
        for item in current_locators:
            if item.get("is_primary"):
                locator_id = str(item.get("locator_id", ""))
                break
        if locator_id is None:
            locator_id = str(current_locators[0].get("locator_id", ""))
    if not locator_id:
        return []

    output = await invoke(
        session,
        InvokeInput(
            organization_id=organization_id,
            user_id=user_id or organization_id,
            task_type="general",
            prompt_version=PROMPT_VERSION,
            capability_id="A3",
            module="results_evidence",
            data_classification="Confidential",
        ),
    )
    degraded = output.result != "ok"
    structured: dict[str, Any] = {}
    if not degraded:
        parsed = _extract_structured_output(output.usage)
        if parsed is not None:
            structured = parsed
        else:
            degraded = True

    return _fixes_from_a3_output(
        locator_id=locator_id,
        current_locators=current_locators,
        structured=structured,
        degraded=degraded,
    )


__all__ = [
    "run_a3_for_locator_cluster",
]
