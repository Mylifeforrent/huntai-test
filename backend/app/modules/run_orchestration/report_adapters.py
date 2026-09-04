"""Multi-format CI report adapters (S-M2-05): junit / allure / playwright / pytest.

归一化产物统一为行级 {name, outcome}，outcome ∈ passed/failed/incomplete
（沿用 M1 既有未冻结枚举，不发明第四套状态机）。
"""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from typing import Any

SUPPORTED_REPORT_ADAPTERS = frozenset({"junit", "allure", "playwright", "pytest"})

# allure-results 是逐文件目录产物，必须由 collect_config / manifest 显式声明路径。
DEFAULT_REPORT_PATHS: dict[str, tuple[str, ...]] = {
    "junit": ("junit.xml",),
    "allure": (),
    "playwright": ("report.json",),
    "pytest": ("report.json",),
}


class ReportParseError(ValueError):
    """显式解析失败：禁止静默截断后当作完整成功（AC-035）。"""


def _junit_child(testcase: ET.Element, local_name: str) -> ET.Element | None:
    for child in testcase:
        if _local_tag(child.tag) == local_name:
            return child
    return None


def _junit_outcome(testcase: ET.Element) -> str:
    if _junit_child(testcase, "failure") is not None or _junit_child(testcase, "error") is not None:
        return "failed"
    if _junit_child(testcase, "skipped") is not None:
        return "incomplete"
    return "passed"


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_junit(report_text: str) -> Iterator[dict[str, str]]:
    # iterparse 流式逐个产出 testcase：>10 万用例报告不整树驻留内存；
    # 若中途遇到畸形 XML，已产出行仍可分批入库（配合上层 partial 标记）。
    try:
        for _event, element in ET.iterparse(io.StringIO(report_text), events=("end",)):
            if _local_tag(element.tag) != "testcase":
                continue
            name = element.get("name") or element.get("classname") or "unknown"
            yield {"name": str(name), "outcome": _junit_outcome(element)}
            element.clear()
    except ET.ParseError as exc:
        raise ReportParseError("junit") from exc


def _outcome_from_status(
    status: object,
    *,
    passed: frozenset[str],
    failed: frozenset[str],
) -> str:
    if not isinstance(status, str):
        return "incomplete"
    if status in passed:
        return "passed"
    if status in failed:
        return "failed"
    return "incomplete"


def _iter_allure(report_text: str) -> Iterator[dict[str, str]]:
    # allure-results：一个 JSON 文件 = 一个测试结果（S-M2-05 选型：逐文件多路径采集）。
    try:
        payload = json.loads(report_text)
    except json.JSONDecodeError as exc:
        raise ReportParseError("allure") from exc
    if not isinstance(payload, dict):
        raise ReportParseError("allure")
    name = payload.get("name")
    yield {
        "name": name.strip() if isinstance(name, str) and name.strip() else "unknown",
        "outcome": _outcome_from_status(
            payload.get("status"),
            passed=frozenset({"passed"}),
            failed=frozenset({"failed", "broken"}),
        ),
    }


def _iter_playwright_specs(
    suites: Any,
    prefix: list[str],
) -> Iterator[dict[str, str]]:
    if not isinstance(suites, list):
        return
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        title = suite.get("title")
        suite_prefix = [*prefix, str(title) if isinstance(title, str) and title.strip() else ""]
        for spec in suite.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            spec_title = spec.get("title")
            tests = spec.get("tests")
            statuses: list[str] = []
            if isinstance(tests, list):
                for test in tests:
                    if not isinstance(test, dict):
                        continue
                    for result in test.get("results") or []:
                        if isinstance(result, dict):
                            statuses.append(str(result.get("status")))
            worst = "passed"
            for status in statuses:
                mapped = _outcome_from_status(
                    status,
                    passed=frozenset({"passed"}),
                    failed=frozenset({"failed", "timedOut", "interrupted"}),
                )
                if mapped == "failed":
                    worst = "failed"
                    break
                if mapped == "incomplete" and worst == "passed":
                    worst = "incomplete"
            name_parts = [part for part in suite_prefix if part] + [
                str(spec_title) if isinstance(spec_title, str) and spec_title.strip() else "unknown"
            ]
            yield {"name": " > ".join(name_parts), "outcome": worst}
        yield from _iter_playwright_specs(suite.get("suites"), suite_prefix)


def _iter_playwright(report_text: str) -> Iterator[dict[str, str]]:
    # Playwright 官方 JSON reporter 单文件（config.playwright JSON reporter）。
    try:
        payload = json.loads(report_text)
    except json.JSONDecodeError as exc:
        raise ReportParseError("playwright") from exc
    if not isinstance(payload, dict):
        raise ReportParseError("playwright")
    yield from _iter_playwright_specs(payload.get("suites"), [])


def _iter_pytest(report_text: str) -> Iterator[dict[str, str]]:
    # pytest-json-report 单文件 JSON。
    try:
        payload = json.loads(report_text)
    except json.JSONDecodeError as exc:
        raise ReportParseError("pytest") from exc
    if not isinstance(payload, dict):
        raise ReportParseError("pytest")
    tests = payload.get("tests")
    if not isinstance(tests, list):
        raise ReportParseError("pytest")
    for test in tests:
        if not isinstance(test, dict):
            continue
        nodeid = test.get("nodeid") or test.get("id")
        yield {
            "name": str(nodeid) if isinstance(nodeid, str) and nodeid.strip() else "unknown",
            "outcome": _outcome_from_status(
                test.get("outcome"),
                passed=frozenset({"passed"}),
                failed=frozenset({"failed", "error"}),
            ),
        }


_PARSERS: dict[str, Callable[[str], Iterator[dict[str, str]]]] = {
    "junit": _iter_junit,
    "allure": _iter_allure,
    "playwright": _iter_playwright,
    "pytest": _iter_pytest,
}


def iter_report_rows(adapter: str, report_text: str) -> Iterator[dict[str, str]]:
    parser = _PARSERS.get(adapter)
    if parser is None:
        raise ReportParseError(f"adapter_unsupported:{adapter}")
    yield from parser(report_text)


def parse_report_rows(adapter: str, report_text: str) -> list[dict[str, str]]:
    return list(iter_report_rows(adapter, report_text))


def _manifest_paths(manifest: dict[str, Any]) -> list[str]:
    for key in ("report_paths", "junit_path", "report_path", "path"):
        raw = manifest.get(key)
        if isinstance(raw, str) and raw.strip():
            return [raw.strip()]
        if isinstance(raw, list):
            paths = [str(item).strip() for item in raw if isinstance(item, str) and item.strip()]
            if paths:
                return paths
    return []


def resolve_report_paths(
    adapter: str,
    *,
    contract: dict[str, Any],
    case: dict[str, Any],
) -> list[str]:
    """collect_config.artifact_path 优先，其次 manifest，最后按适配器默认。"""
    paths: list[str] = []
    job_binding = case.get("job_binding")
    if isinstance(job_binding, dict):
        collect = job_binding.get("collect_config")
        if isinstance(collect, dict):
            raw = collect.get("artifact_path")
            if isinstance(raw, str) and raw.strip():
                paths = [raw.strip()]
            elif isinstance(raw, list):
                paths = [
                    str(item).strip() for item in raw if isinstance(item, str) and item.strip()
                ]
    if not paths:
        manifest = contract.get("artifact_manifest")
        if isinstance(manifest, dict):
            paths = _manifest_paths(manifest)
    if not paths:
        paths = list(DEFAULT_REPORT_PATHS.get(adapter, ()))
    return paths


__all__ = [
    "DEFAULT_REPORT_PATHS",
    "ReportParseError",
    "SUPPORTED_REPORT_ADAPTERS",
    "iter_report_rows",
    "parse_report_rows",
    "resolve_report_paths",
]
