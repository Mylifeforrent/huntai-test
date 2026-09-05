"""S-M2-05 report adapters and log chunk helpers."""

from __future__ import annotations

import pytest

from app.modules.run_orchestration.external_ci_executor import split_log_payload
from app.modules.run_orchestration.report_adapters import (
    ReportParseError,
    iter_report_rows,
    parse_report_rows,
)


def test_junit_iterparse_and_namespaced_tags() -> None:
    xml = """<?xml version="1.0"?>
    <ns:testsuite xmlns:ns="urn:junit">
      <ns:testcase name="ok"/>
      <ns:testcase name="boom"><ns:failure message="x"/></ns:testcase>
      <ns:testcase name="skip"><ns:skipped/></ns:testcase>
    </ns:testsuite>
    """
    rows = parse_report_rows("junit", xml)
    assert [row["outcome"] for row in rows] == ["passed", "failed", "incomplete"]


def test_junit_malformed_raises() -> None:
    with pytest.raises(ReportParseError):
        parse_report_rows("junit", "<testsuite><testcase></notclosed>")


def test_allure_parses_one_json_object_per_file() -> None:
    rows = parse_report_rows("allure", '{"name": "login", "status": "broken"}')
    assert rows == [{"name": "login", "outcome": "failed"}]


def test_allure_multi_file_must_be_parsed_separately() -> None:
    file_a = '{"name": "a", "status": "passed"}'
    file_b = '{"name": "b", "status": "failed"}'
    with pytest.raises(ReportParseError):
        parse_report_rows("allure", file_a + "\n" + file_b)
    combined = list(iter_report_rows("allure", file_a)) + list(iter_report_rows("allure", file_b))
    assert [row["name"] for row in combined] == ["a", "b"]


def test_playwright_json_reporter_worst_status() -> None:
    payload = """
    {"suites":[{"title":"s","specs":[{"title":"click",
      "tests":[{"results":[{"status":"passed"},{"status":"timedOut"}]}]}]}]}
    """
    rows = parse_report_rows("playwright", payload)
    assert rows == [{"name": "s > click", "outcome": "failed"}]


def test_pytest_json_report() -> None:
    payload = (
        '{"tests":[{"nodeid":"t.py::ok","outcome":"passed"},'
        '{"nodeid":"t.py::err","outcome":"error"}]}'
    )
    rows = parse_report_rows("pytest", payload)
    assert [row["outcome"] for row in rows] == ["passed", "failed"]


def test_split_log_payload_does_not_skip_bytes() -> None:
    payload = b"abcdefghijklmnopqrstuvwxyz"
    chunks, truncated = split_log_payload(
        payload,
        chunk_size=10,
        max_total=100,
        already_written=0,
    )
    assert truncated is False
    assert b"".join(chunks) == payload
    assert all(len(chunk) <= 10 for chunk in chunks)


def test_split_log_payload_marks_truncated_without_dropping_kept_bytes() -> None:
    payload = b"0123456789abcdef"
    chunks, truncated = split_log_payload(
        payload,
        chunk_size=4,
        max_total=10,
        already_written=0,
    )
    assert truncated is True
    kept = b"".join(chunks)
    assert kept == b"0123456789"
    assert len(kept) == 10
