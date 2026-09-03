"""In-process HTTP runner for script × platform_executor."""

from __future__ import annotations

import json
import time
from typing import Any, Protocol
from urllib.parse import urljoin

import httpx

VALID_ASSERTION_TYPES = frozenset(
    {"status_code", "response_time", "contains", "json_path", "header", "equals"}
)


class HttpClient(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: str | bytes | None = None,
    ) -> httpx.Response: ...


def _normalize_base_url(base: str) -> str:
    return base if base.endswith("/") else f"{base}/"


async def execute_request_step(
    client: HttpClient,
    *,
    base_url: str,
    step: dict[str, Any],
) -> dict[str, Any]:
    params = step.get("params")
    if not isinstance(params, dict):
        return {"ok": False, "error": "invalid_step_params"}
    method = str(params.get("method", "GET")).upper()
    path = str(params.get("path", "/"))
    headers_raw = params.get("headers")
    headers: dict[str, str] = {}
    if isinstance(headers_raw, dict):
        headers = {str(k): str(v) for k, v in headers_raw.items()}
    body = params.get("body")
    content: str | bytes | None = None
    if body is not None:
        content = body if isinstance(body, (str, bytes)) else json.dumps(body)
    url = urljoin(_normalize_base_url(base_url), path.lstrip("/"))
    started = time.perf_counter()
    response = await client.request(method, url, headers=headers or None, content=content)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    text = response.text
    return {
        "ok": True,
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body_text": text[:4096],
        "elapsed_ms": elapsed_ms,
    }


def evaluate_assertion(assertion: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    atype = str(assertion.get("type", ""))
    if atype not in VALID_ASSERTION_TYPES:
        return {"type": atype, "passed": False, "error": "unknown_assertion_type"}
    expected = assertion.get("expected")
    if atype == "status_code":
        actual = observation.get("status_code")
        passed = actual == expected
        return {"type": atype, "passed": passed, "expected": expected, "actual": actual}
    if atype == "response_time":
        actual = observation.get("elapsed_ms")
        if expected is None:
            return {"type": atype, "passed": False, "error": "invalid_expected"}
        try:
            limit = int(str(expected))
        except TypeError:
            return {"type": atype, "passed": False, "error": "invalid_expected"}
        except ValueError:
            return {"type": atype, "passed": False, "error": "invalid_expected"}
        passed = isinstance(actual, int) and actual <= limit
        return {"type": atype, "passed": passed, "expected": limit, "actual": actual}
    if atype == "contains":
        body = str(observation.get("body_text", ""))
        needle = str(expected) if expected is not None else ""
        passed = needle in body
        return {"type": atype, "passed": passed, "expected": needle}
    if atype == "equals":
        body = str(observation.get("body_text", ""))
        passed = body == str(expected)
        return {"type": atype, "passed": passed, "expected": expected, "actual": body}
    if atype == "header":
        headers = observation.get("headers")
        if not isinstance(headers, dict):
            return {"type": atype, "passed": False, "error": "missing_headers"}
        expr = str(assertion.get("expression", ""))
        actual = headers.get(expr)
        passed = actual == expected
        return {
            "type": atype,
            "passed": passed,
            "expression": expr,
            "expected": expected,
            "actual": actual,
        }
    if atype == "json_path":
        body = observation.get("body_text", "")
        try:
            data = json.loads(str(body))
        except json.JSONDecodeError:
            return {"type": atype, "passed": False, "error": "invalid_json"}
        expr = str(assertion.get("expression", ""))
        actual = _json_path_simple(data, expr)
        passed = actual == expected
        return {
            "type": atype,
            "passed": passed,
            "expression": expr,
            "expected": expected,
            "actual": actual,
        }
    return {"type": atype, "passed": False, "error": "unsupported"}


def _json_path_simple(data: Any, expression: str) -> Any:
    if not expression.startswith("$."):
        return None
    parts = expression[2:].split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


async def run_case_http(
    client: HttpClient,
    *,
    base_url: str,
    steps: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    step_records: list[dict[str, Any]] = []
    last_observation: dict[str, Any] | None = None
    for index, step in enumerate(steps):
        action = str(step.get("action", ""))
        if action != "request":
            step_records.append(
                {
                    "step_index": index,
                    "action": step,
                    "assertion_results": None,
                    "is_incomplete": True,
                    "error": "unsupported_action",
                }
            )
            return "failed", step_records, []
        observation = await execute_request_step(client, base_url=base_url, step=step)
        last_observation = observation
        step_records.append(
            {
                "step_index": index,
                "action": step,
                "observation": {
                    "status_code": observation.get("status_code"),
                    "elapsed_ms": observation.get("elapsed_ms"),
                },
                "assertion_results": None,
                "is_incomplete": not observation.get("ok", False),
            }
        )
        if not observation.get("ok", False):
            return "failed", step_records, []

    assertion_results: list[dict[str, Any]] = []
    if last_observation is None:
        return "incomplete", step_records, assertion_results
    all_passed = True
    for assertion in assertions:
        if not isinstance(assertion, dict):
            all_passed = False
            assertion_results.append({"passed": False, "error": "invalid_assertion"})
            continue
        result = evaluate_assertion(assertion, last_observation)
        assertion_results.append(result)
        if not result.get("passed", False):
            all_passed = False
    if step_records:
        step_records[-1]["assertion_results"] = assertion_results
    return ("passed" if all_passed else "failed"), step_records, assertion_results
