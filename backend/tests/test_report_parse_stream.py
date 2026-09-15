"""D15 streaming report parse: iterator batches, timeout, running worst."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.results_evidence import repository as results_repo
from app.modules.run_orchestration import repository as run_repo
from app.modules.run_orchestration.external_ci_executor import (
    _write_report_results,
    collect_reports_for_run,
)
from app.modules.run_orchestration.report_adapters import (
    iter_report_rows_from_files,
    resolve_report_paths,
)
from tests.test_run_helpers import activate_external_ci_env, create_active_referenced_case


class _TrackingIterator:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = iter(rows)
        self.pulls = 0
        self.exhausted = False

    def __iter__(self) -> Iterator[dict[str, str]]:
        return self

    def __next__(self) -> dict[str, str]:
        self.pulls += 1
        try:
            return next(self._rows)
        except StopIteration:
            self.exhausted = True
            raise


async def _seed_run_and_case(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> tuple[object, dict[str, object], dict[str, object]]:
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    env = await activate_external_ci_env(client, db_session, seeded_identity)
    case = await create_active_referenced_case(client, project_id=project_id, env_id=env["id"])
    now = datetime.now(UTC)
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(str(env["id"])),
        execution_source="external_ci",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_EXTERNAL",
        snapshot={
            "case_ids": [case["id"]],
            "execution_source": "external_ci",
        },
    )
    await db_session.commit()
    case_row = {
        "id": uuid.UUID(str(case["id"])),
        "version_id": case.get("current_version_id"),
    }
    return run, case_row, case


@pytest.mark.asyncio
async def test_write_starts_before_iterator_exhausted(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, case, _raw_case = await _seed_run_and_case(client, db_session, seeded_identity)
    rows = [{"name": f"t{i}", "outcome": "passed"} for i in range(10)]
    tracker = _TrackingIterator(rows)
    step_calls = 0

    async def _track_append(*args: object, **kwargs: object) -> uuid.UUID:
        nonlocal step_calls
        step_calls += 1
        if step_calls == 1:
            assert not tracker.exhausted
            assert tracker.pulls < len(rows)
        from app.modules.results_evidence.command_port import append_step_run as real_append

        return await real_append(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor._report_batch_rows",
        lambda: 2,
    )
    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor.append_step_run",
        _track_append,
    )
    now = datetime.now(UTC)
    all_passed, accounted, parse_incomplete = await _write_report_results(
        db_session,
        run=run,
        cases=[case],
        contracts=[{"case": case}],
        adapter="junit",
        report_rows_iter=iter(tracker),
        report_files=[("junit.xml", "<testsuite/>")],
        now=now,
    )
    assert accounted is True
    assert parse_incomplete is False
    assert all_passed is True
    assert step_calls >= 1
    assert tracker.exhausted


@pytest.mark.asyncio
async def test_timeout_leaves_partial_rows_and_not_succeeded(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, case, _raw_case = await _seed_run_and_case(client, db_session, seeded_identity)
    rows = [{"name": f"t{i}", "outcome": "passed"} for i in range(20)]
    clock = {"value": 100.0}

    def fake_monotonic() -> float:
        return clock["value"]

    async def _advance_clock_after_step(*args: object, **kwargs: object) -> uuid.UUID:
        clock["value"] += 200.0
        from app.modules.results_evidence.command_port import append_step_run as real_append

        return await real_append(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor.time.monotonic",
        fake_monotonic,
    )
    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor.append_step_run",
        _advance_clock_after_step,
    )
    monkeypatch.setenv("REPORT_PARSE_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor._report_batch_rows",
        lambda: 5,
    )
    now = datetime.now(UTC)
    all_passed, accounted, parse_incomplete = await _write_report_results(
        db_session,
        run=run,
        cases=[case],
        contracts=[{"case": case}],
        adapter="junit",
        report_rows_iter=iter(rows),
        report_files=[("junit.xml", "<testsuite/>")],
        now=now,
    )
    get_settings.cache_clear()
    assert accounted is True
    assert parse_incomplete is True
    assert all_passed is True
    case_results = await results_repo.list_case_results_for_run(
        db_session,
        organization_id=run.organization_id,
        test_run_id=run.id,
    )
    assert len(case_results) == 1
    assert case_results[0].is_partial is True
    steps = await results_repo.list_step_runs_for_case_result(
        db_session,
        organization_id=run.organization_id,
        case_result_id=case_results[0].id,
    )
    assert len(steps) >= 1
    assert len(steps) < len(rows)


@pytest.mark.asyncio
async def test_small_junit_completes_with_is_partial_false(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, case, _raw_case = await _seed_run_and_case(client, db_session, seeded_identity)
    junit = """<?xml version="1.0"?>
    <testsuite>
      <testcase name="a"/>
      <testcase name="b"><failure message="x"/></testcase>
    </testsuite>
    """
    monkeypatch.delenv("REPORT_PARSE_TIMEOUT_SECONDS", raising=False)
    get_settings.cache_clear()
    now = datetime.now(UTC)
    all_passed, accounted, parse_incomplete = await _write_report_results(
        db_session,
        run=run,
        cases=[case],
        contracts=[{"case": case}],
        adapter="junit",
        report_rows_iter=iter_report_rows_from_files("junit", [("junit.xml", junit)]),
        report_files=[("junit.xml", junit)],
        now=now,
    )
    assert accounted is True
    assert parse_incomplete is False
    assert all_passed is False
    case_results = await results_repo.list_case_results_for_run(
        db_session,
        organization_id=run.organization_id,
        test_run_id=run.id,
    )
    assert len(case_results) == 1
    assert case_results[0].is_partial is False
    assert case_results[0].outcome == "failed"
    steps = await results_repo.list_step_runs_for_case_result(
        db_session,
        organization_id=run.organization_id,
        case_result_id=case_results[0].id,
    )
    assert len(steps) == 1


@pytest.mark.asyncio
async def test_running_worst_updates_to_failed_after_later_batch(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, case, _raw_case = await _seed_run_and_case(client, db_session, seeded_identity)
    rows = [{"name": f"ok{i}", "outcome": "passed"} for i in range(4)] + [
        {"name": "boom", "outcome": "failed"}
    ]
    monkeypatch.delenv("REPORT_PARSE_TIMEOUT_SECONDS", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.modules.run_orchestration.external_ci_executor._report_batch_rows",
        lambda: 2,
    )
    now = datetime.now(UTC)
    all_passed, accounted, parse_incomplete = await _write_report_results(
        db_session,
        run=run,
        cases=[case],
        contracts=[{"case": case}],
        adapter="junit",
        report_rows_iter=iter(rows),
        report_files=[("junit.xml", "<testsuite/>")],
        now=now,
    )
    assert accounted is True
    assert parse_incomplete is False
    assert all_passed is False
    case_results = await results_repo.list_case_results_for_run(
        db_session,
        organization_id=run.organization_id,
        test_run_id=run.id,
    )
    assert case_results[0].outcome == "failed"
    assert case_results[0].is_partial is False


@pytest.mark.asyncio
async def test_allure_without_declared_path_is_report_path_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    paths = resolve_report_paths(
        "allure",
        contract={"artifact_manifest": {}},
        case={"job_binding": {}},
    )
    assert paths == []
    run, case, _raw_case = await _seed_run_and_case(client, db_session, seeded_identity)
    allure_case = {"id": case["id"], "job_binding": {}}
    contracts = [
        {
            "case": allure_case,
            "contract": {"report_adapter": "allure", "artifact_manifest": {}},
            "job_id": "smoke-suite",
        }
    ]
    run.result_summary = {
        "ci": {
            "collect_state": "collecting",
            "job_id": "smoke-suite",
            "build_number": 1,
        }
    }
    await db_session.commit()

    class _Client:
        async def get(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("artifact fetch should not run")

    with patch(
        "app.modules.run_orchestration.external_ci_executor._collect_build_logs",
        return_value=None,
    ):
        terminal = await collect_reports_for_run(
            db_session,
            run=run,
            contracts=contracts,
            env_info={},
            client=_Client(),  # type: ignore[arg-type]
            token="t",
            endpoint="https://ci.example.com",
            ci={"build_number": 1, "job_id": "smoke-suite"},
        )
    assert terminal is True
    await db_session.refresh(run)
    assert run.status == "FAILED"
    assert run.result_summary["ci"]["reason"] == "report_path_missing"
