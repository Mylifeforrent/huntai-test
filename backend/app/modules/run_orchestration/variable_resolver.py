"""Two-layer variable resolution for TestRun VALIDATING."""

from __future__ import annotations

import re
from typing import Any

FUNC_PATTERN = re.compile(r"\$\{[^}]+\}")
VAR_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


def _collect_strings(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, out)


def collect_scannable_strings(*parts: Any) -> list[str]:
    collected: list[str] = []
    for part in parts:
        _collect_strings(part, collected)
    return collected


def find_unresolved_functions(texts: list[str]) -> list[str]:
    unresolved: list[str] = []
    for text in texts:
        for match in FUNC_PATTERN.finditer(text):
            unresolved.append(match.group(0))
    return unresolved


def resolve_text(text: str, bindings: dict[str, str]) -> tuple[str, list[str]]:
    errors: list[str] = []
    if FUNC_PATTERN.search(text):
        for match in FUNC_PATTERN.finditer(text):
            errors.append(match.group(0))
        return text, errors

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name not in bindings:
            errors.append(f"{{{{{name}}}}}")
            return match.group(0)
        return bindings[name]

    resolved = VAR_PATTERN.sub(replacer, text)
    return resolved, errors


def resolve_value(value: Any, bindings: dict[str, str]) -> tuple[Any, list[str]]:
    if isinstance(value, str):
        resolved, errors = resolve_text(value, bindings)
        return resolved, errors
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        nested_errors: list[str] = []
        for key, item in value.items():
            resolved_item, item_errors = resolve_value(item, bindings)
            out[key] = resolved_item
            nested_errors.extend(item_errors)
        return out, nested_errors
    if isinstance(value, list):
        out_list: list[Any] = []
        list_errors: list[str] = []
        for item in value:
            resolved_item, item_errors = resolve_value(item, bindings)
            out_list.append(resolved_item)
            list_errors.extend(item_errors)
        return out_list, list_errors
    return value, []


def build_bindings(params: dict[str, Any] | None) -> dict[str, str]:
    bindings: dict[str, str] = {}
    if not params:
        return bindings
    for key, value in params.items():
        if isinstance(value, (str, int, float, bool)):
            bindings[key] = str(value)
    return bindings


def validate_and_resolve_snapshot(
    *,
    params: dict[str, Any] | None,
    steps: list[Any],
    assertions: list[Any],
) -> tuple[list[Any], list[Any], list[str]]:
    bindings = build_bindings(params)
    texts = collect_scannable_strings(params, steps, assertions)
    func_errors = find_unresolved_functions(texts)

    resolved_steps, step_errors = resolve_value(steps, bindings)
    resolved_assertions, assertion_errors = resolve_value(assertions, bindings)
    all_errors = list(dict.fromkeys(func_errors + step_errors + assertion_errors))
    assert isinstance(resolved_steps, list)
    assert isinstance(resolved_assertions, list)
    return resolved_steps, resolved_assertions, all_errors
