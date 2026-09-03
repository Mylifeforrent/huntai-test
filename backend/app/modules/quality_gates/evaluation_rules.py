"""Pure gate-evaluation helpers (no ORM, no cross-module repos)."""

from __future__ import annotations

from typing import Any

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED"})
SKIP_STATUSES = frozenset({"CANCELLED", "TIMEOUT"})
VALID_INSERT_RESULTS = frozenset({"pass", "fail"})


def is_partial_report(
    *,
    result_summary: dict[str, Any] | None,
    case_results: list[dict[str, Any]],
) -> bool:
    summary = result_summary or {}
    if summary.get("partial") is True or summary.get("incomplete_collect") is True:
        return True
    ci = summary.get("ci")
    if isinstance(ci, dict):
        collect_state = ci.get("collect_state")
        if collect_state is not None and collect_state != "done":
            return True
    return any(
        row.get("is_partial") is True or row.get("outcome") == "incomplete" for row in case_results
    )


def compute_pass_rate(case_results: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    total = len(case_results)
    if total == 0:
        return 0.0, {"passed": 0, "total": 0, "pass_rate": 0.0}
    passed = sum(1 for row in case_results if row.get("outcome") == "passed")
    rate = passed / total * 100.0
    return rate, {"passed": passed, "total": total, "pass_rate": rate}


def build_threshold_details(
    *,
    thresholds: dict[str, Any],
    pass_rate: float,
    pass_detail: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    min_pass_rate = float(thresholds["min_pass_rate"])
    pass_ok = pass_rate >= min_pass_rate
    details: dict[str, Any] = {
        "min_pass_rate": {
            "threshold": min_pass_rate,
            "actual": pass_rate,
            "passed": pass_ok,
            **pass_detail,
        },
        "max_p95_ms": {
            "threshold": thresholds["max_p95_ms"],
            "not_measured": True,
        },
        "max_error_rate": {
            "threshold": thresholds["max_error_rate"],
            "not_measured": True,
        },
    }
    result = "pass" if pass_ok else "fail"
    return details, result
