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
    perf_metrics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """FR-12: perf runs evaluate p95/error_rate in the same pipeline.

    Functional runs leave p95/error_rate as not_measured (no data source);
    perf runs must carry metrics — the caller fail-closes otherwise.
    """
    min_pass_rate = float(thresholds["min_pass_rate"])
    pass_ok = pass_rate >= min_pass_rate
    all_ok = pass_ok
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
    if perf_metrics is not None:
        p95_raw = perf_metrics.get("p95_ms")
        error_raw = perf_metrics.get("error_rate")
        if isinstance(p95_raw, (int, float)):
            p95_threshold = float(thresholds["max_p95_ms"])
            p95_ok = float(p95_raw) <= p95_threshold
            details["max_p95_ms"] = {
                "threshold": p95_threshold,
                "actual": float(p95_raw),
                "passed": p95_ok,
                "not_measured": False,
            }
            all_ok = all_ok and p95_ok
        if isinstance(error_raw, (int, float)):
            error_threshold = float(thresholds["max_error_rate"])
            error_ok = float(error_raw) <= error_threshold
            details["max_error_rate"] = {
                "threshold": error_threshold,
                "actual": float(error_raw),
                "passed": error_ok,
                "not_measured": False,
            }
            all_ok = all_ok and error_ok
    result = "pass" if all_ok else "fail"
    return details, result
