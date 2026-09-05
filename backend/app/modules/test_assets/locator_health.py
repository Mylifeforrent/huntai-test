"""Locator health projection helpers (not a 24th domain object)."""

from __future__ import annotations

import hashlib
from typing import Any

WEB_LOCATOR_ACTIONS = frozenset({"click", "fill", "type", "select", "check", "hover"})


def stable_locator_id(strategy: str, expression: str) -> str:
    digest = hashlib.sha256(f"{strategy}|{expression}".encode()).hexdigest()[:12]
    return f"loc-{digest}"


def extract_locator_health_from_steps(steps: list[Any]) -> list[dict[str, Any]]:
    locators: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        action_name = str(step.get("action", ""))
        if action_name not in WEB_LOCATOR_ACTIONS:
            continue
        params = step.get("params")
        if not isinstance(params, dict):
            continue
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            continue
        strategy_raw = params.get("strategy")
        strategy = (
            str(strategy_raw).strip()
            if isinstance(strategy_raw, str) and strategy_raw.strip()
            else "css"
        )
        expression = selector.strip()
        locator_id = stable_locator_id(strategy, expression)
        if locator_id in seen_ids:
            continue
        seen_ids.add(locator_id)
        locators.append(
            {
                "locator_id": locator_id,
                "strategy": strategy,
                "is_primary": len(locators) == 0,
                "expression": expression,
                "health": "unknown",
            }
        )
    return locators
