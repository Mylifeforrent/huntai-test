"""Background TestRun orchestration: VALIDATING → execute/cancel → terminal."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.execution_registry import query_port as execution_query
from app.modules.quality_gates.command_port import schedule_gate_evaluation
from app.modules.results_evidence.command_port import (
    CaseResultWrite,
    StepRunWrite,
    append_case_result,
    append_step_run,
    schedule_failure_triage,
)
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.http_runner import run_case_http
from app.modules.run_orchestration.models import TestRun
from app.modules.run_orchestration.variable_resolver import validate_and_resolve_snapshot
from app.modules.test_assets import query_port as test_assets_query

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"})


def _fail_summary(reason: str, *, details: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    if details:
        payload["details"] = details
    return payload


async def _validate_run(
    session: AsyncSession,
    *,
    run: TestRun,
    env_info: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    _ = env_info
    snapshot = dict(run.snapshot)
    case_ids_raw = snapshot.get("case_ids", [])
    if not isinstance(case_ids_raw, list) or not case_ids_raw:
        return False, _fail_summary("missing_case_ids"), []
    case_ids = [uuid.UUID(str(cid)) for cid in case_ids_raw]
    cases = await test_assets_query.get_cases_for_run_validation(
        session,
        organization_id=run.organization_id,
        project_id=run.project_id,
        case_ids=case_ids,
    )
    if len(cases) != len(case_ids):
        return False, _fail_summary("case_not_found"), []
    for case in cases:
        if case["lifecycle_status"] != "ACTIVE":
            return False, _fail_summary("case_not_active", details=[str(case["id"])]), []
        if case["validity"] != "valid":
            return False, _fail_summary("case_invalid", details=[str(case["id"])]), []
        if run.execution_source == "agent" and case["execution_mode"] != "agent":
            return False, _fail_summary("execution_mode_mismatch"), []
        if run.execution_source == "script" and case["execution_mode"] != "script":
            return False, _fail_summary("execution_mode_mismatch"), []

    if run.execution_source == "external_ci":
        for case in cases:
            if not case.get("job_binding"):
                return False, _fail_summary("missing_job_binding", details=[str(case["id"])]), []

    params = snapshot.get("params_redacted")
    params_dict = params if isinstance(params, dict) else {}
    resolved_cases: list[dict[str, Any]] = []
    for case in cases:
        steps = case.get("steps", [])
        assertions = case.get("assertions", [])
        _, _, errors = validate_and_resolve_snapshot(
            params=params_dict,
            steps=steps,
            assertions=assertions,
        )
        if errors:
            return False, _fail_summary("variable_unresolved", details=errors), []
        resolved_cases.append(case)

    return True, None, resolved_cases


async def _load_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> TestRun | None:
    return await repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        for_update=True,
    )


async def complete_stopping_run(
    session: AsyncSession,
    *,
    run: TestRun,
    now: datetime,
) -> None:
    if run.status == "STOPPING":
        await repo.update_test_run_status(
            session,
            run=run,
            new_status="CANCELLED",
            updated_at=now,
        )


async def _invoke_playwright_worker(payload: dict[str, Any]) -> int:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle)
        payload_path = handle.name
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.modules.run_orchestration.playwright_worker",
            payload_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        await proc.communicate()
        return int(proc.returncode or 0)
    finally:
        Path(payload_path).unlink(missing_ok=True)


async def _execute_web_case(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    case: dict[str, Any],
    params_dict: dict[str, Any],
    created_by: uuid.UUID | None,
) -> str:
    case_payload = dict(case)
    case_payload["id"] = str(case["id"])
    if case.get("version_id") is not None:
        case_payload["version_id"] = str(case["version_id"])
    payload = {
        "organization_id": str(organization_id),
        "test_run_id": str(test_run_id),
        "created_by": str(created_by) if created_by else None,
        "case": case_payload,
        "params": params_dict,
    }
    exit_code = await _invoke_playwright_worker(payload)
    if exit_code != 0:
        return "failed"
    factory = get_session_factory()
    async with factory() as session:
        from app.modules.results_evidence import repository as evidence_repo

        results = await evidence_repo.list_case_results_for_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        case_id = uuid.UUID(str(case["id"]))
        matched = [row for row in results if row.test_case_id == case_id]
        await session.commit()
    if not matched:
        return "failed"
    return matched[-1].outcome


async def _execute_script_run(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    cases: list[dict[str, Any]],
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        if run is None or run.status != "RUNNING":
            await session.commit()
            return
        params = run.snapshot.get("params_redacted")
        params_dict = params if isinstance(params, dict) else {}
        base_url = str(params_dict.get("TARGET_ENV", "")).strip()
        created_by = run.created_by
        now = datetime.now(UTC)
        if not base_url:
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="FAILED",
                updated_at=now,
                result_summary=_fail_summary("missing_target_env"),
            )
            await session.commit()
            return
        await session.commit()

    all_passed = True
    async with httpx.AsyncClient(timeout=30.0) as client:
        for case in cases:
            async with factory() as session:
                run = await _load_run(
                    session, organization_id=organization_id, test_run_id=test_run_id
                )
                now = datetime.now(UTC)
                if run is None:
                    await session.commit()
                    return
                if run.status == "STOPPING" or run.stop_signal_at is not None:
                    await complete_stopping_run(session, run=run, now=now)
                    await session.commit()
                    return
                if run.status != "RUNNING":
                    await session.commit()
                    return
                await session.commit()

            steps = case.get("steps", [])
            assertions = case.get("assertions", [])
            case_type = str(case.get("case_type", "api"))
            if case_type == "web":
                outcome = await _execute_web_case(
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                    case=case,
                    params_dict=params_dict,
                    created_by=created_by,
                )
                if outcome != "passed":
                    all_passed = False
                async with factory() as session:
                    run = await _load_run(
                        session, organization_id=organization_id, test_run_id=test_run_id
                    )
                    now = datetime.now(UTC)
                    if run is None:
                        await session.commit()
                        return
                    if run.status == "STOPPING" or run.stop_signal_at is not None:
                        await complete_stopping_run(session, run=run, now=now)
                        await session.commit()
                        return
                    if run.status != "RUNNING":
                        await session.commit()
                        return
                    await repo.update_test_run_status(
                        session,
                        run=run,
                        new_status="RUNNING",
                        updated_at=now,
                        heartbeat=True,
                    )
                    await session.commit()
                continue
            if case_type not in {"api"}:
                async with factory() as session:
                    run = await _load_run(
                        session, organization_id=organization_id, test_run_id=test_run_id
                    )
                    now = datetime.now(UTC)
                    if run is not None and run.status == "RUNNING":
                        version_raw = case.get("version_id")
                        version_id = uuid.UUID(str(version_raw)) if version_raw else None
                        await append_case_result(
                            session,
                            organization_id=organization_id,
                            created_by=created_by,
                            created_at=now,
                            payload=CaseResultWrite(
                                test_run_id=test_run_id,
                                test_case_id=uuid.UUID(str(case["id"])),
                                test_case_version_id=version_id,
                                attempt_seq=1,
                                outcome="incomplete",
                                normalized_summary=_fail_summary("unsupported_case_type"),
                            ),
                        )
                        all_passed = False
                        await repo.update_test_run_status(
                            session,
                            run=run,
                            new_status="RUNNING",
                            updated_at=now,
                            heartbeat=True,
                        )
                    await session.commit()
                continue
            resolved_steps, resolved_assertions, errors = validate_and_resolve_snapshot(
                params=params_dict,
                steps=steps,
                assertions=assertions,
            )
            if errors:
                async with factory() as session:
                    run = await _load_run(
                        session, organization_id=organization_id, test_run_id=test_run_id
                    )
                    if run is not None and run.status == "RUNNING":
                        await repo.update_test_run_status(
                            session,
                            run=run,
                            new_status="FAILED",
                            updated_at=datetime.now(UTC),
                            result_summary=_fail_summary("variable_unresolved", details=errors),
                        )
                    await session.commit()
                return
            outcome, step_records, _ = await run_case_http(
                client,
                base_url=base_url,
                steps=resolved_steps,
                assertions=resolved_assertions,
            )
            async with factory() as session:
                run = await _load_run(
                    session, organization_id=organization_id, test_run_id=test_run_id
                )
                now = datetime.now(UTC)
                if run is None:
                    await session.commit()
                    return
                if run.status == "STOPPING" or run.stop_signal_at is not None:
                    await complete_stopping_run(session, run=run, now=now)
                    await session.commit()
                    return
                if run.status != "RUNNING":
                    await session.commit()
                    return
                version_raw = case.get("version_id")
                version_id = uuid.UUID(str(version_raw)) if version_raw else None
                normalized_summary: dict[str, Any] | None = None
                if outcome != "passed" and step_records:
                    for record in step_records:
                        observation = record.get("observation")
                        if isinstance(observation, dict) and "status_code" in observation:
                            path_val = None
                            action = record.get("action")
                            if isinstance(action, dict):
                                params = action.get("params")
                                if isinstance(params, dict) and isinstance(params.get("path"), str):
                                    path_val = params["path"]
                            normalized_summary = {
                                "status_code": observation.get("status_code"),
                                "path": path_val,
                            }
                            break
                case_result_id = await append_case_result(
                    session,
                    organization_id=organization_id,
                    created_by=created_by,
                    created_at=now,
                    payload=CaseResultWrite(
                        test_run_id=test_run_id,
                        test_case_id=uuid.UUID(str(case["id"])),
                        test_case_version_id=version_id,
                        attempt_seq=1,
                        outcome=outcome,
                        normalized_summary=normalized_summary,
                    ),
                )
                for record in step_records:
                    await append_step_run(
                        session,
                        organization_id=organization_id,
                        created_by=created_by,
                        created_at=now,
                        payload=StepRunWrite(
                            case_result_id=case_result_id,
                            step_index=int(record["step_index"]),
                            action=record.get("action")
                            if isinstance(record.get("action"), dict)
                            else None,
                            assertion_results=record.get("assertion_results"),
                            is_incomplete=bool(record.get("is_incomplete", False)),
                        ),
                    )
                if outcome != "passed":
                    all_passed = False
                await repo.update_test_run_status(
                    session,
                    run=run,
                    new_status="RUNNING",
                    updated_at=now,
                    heartbeat=True,
                )
                await session.commit()

    async with factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        now = datetime.now(UTC)
        if run is not None and run.status == "RUNNING":
            final_status = "SUCCEEDED" if all_passed else "FAILED"
            await repo.update_test_run_status(
                session,
                run=run,
                new_status=final_status,
                updated_at=now,
                result_summary={
                    "cases": len(cases),
                    "outcome": final_status.lower(),
                    "clustering": {
                        "generation_status": "pending",
                        "degraded": False,
                        "unclustered_refs": [],
                    },
                },
            )
        elif run is not None:
            await complete_stopping_run(session, run=run, now=now)
        await session.commit()
    await schedule_failure_triage(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    await schedule_gate_evaluation(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )


async def run_test_run_background(*, organization_id: uuid.UUID, test_run_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as session:
        run = await repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is None or run.status != "PENDING":
            await session.commit()
            return
        now = datetime.now(UTC)
        await repo.update_test_run_status(
            session,
            run=run,
            new_status="VALIDATING",
            updated_at=now,
        )
        await session.commit()

    async with factory() as session:
        run = await repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is None or run.status != "VALIDATING":
            await session.commit()
            return
        now = datetime.now(UTC)
        if run.stop_signal_at is not None:
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="CANCELLED",
                updated_at=now,
            )
            await session.commit()
            return

        env_info = await execution_query.get_environment_for_start(
            session,
            organization_id=organization_id,
            environment_id=run.env_id,
        )
        if env_info is None or env_info["status"] != "ACTIVE":
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="FAILED",
                updated_at=now,
                result_summary=_fail_summary("env_not_active"),
            )
            await session.commit()
            return

        ok, fail_summary, cases = await _validate_run(session, run=run, env_info=env_info)
        if not ok:
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="FAILED",
                updated_at=now,
                result_summary=fail_summary,
            )
            await session.commit()
            return

        if run.execution_source == "external_ci":
            await session.commit()
            from app.modules.run_orchestration.external_ci_executor import (
                execute_external_ci_run,
                validate_external_ci_run,
            )

            async with factory() as ext_session:
                run_ro = await repo.get_test_run(
                    ext_session,
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                )
                if run_ro is None or run_ro.status != "VALIDATING":
                    await ext_session.commit()
                    return
                env_info_fresh = await execution_query.get_environment_for_start(
                    ext_session,
                    organization_id=organization_id,
                    environment_id=run_ro.env_id,
                )
                if env_info_fresh is None:
                    await ext_session.commit()
                    return
                case_ids_raw = run_ro.snapshot.get("case_ids", [])
                case_ids_parsed = (
                    [uuid.UUID(str(cid)) for cid in case_ids_raw]
                    if isinstance(case_ids_raw, list)
                    else []
                )
                cases_fresh = await test_assets_query.get_cases_for_run_validation(
                    ext_session,
                    organization_id=organization_id,
                    project_id=run_ro.project_id,
                    case_ids=case_ids_parsed,
                )
                ext_ok, ext_fail, contracts = await validate_external_ci_run(
                    ext_session,
                    run=run_ro,
                    env_info=env_info_fresh,
                    cases=cases_fresh,
                )
                if not ext_ok:
                    run_locked = await repo.get_test_run(
                        ext_session,
                        organization_id=organization_id,
                        test_run_id=test_run_id,
                        for_update=True,
                    )
                    if run_locked is not None and run_locked.status == "VALIDATING":
                        await repo.update_test_run_status(
                            ext_session,
                            run=run_locked,
                            new_status="FAILED",
                            updated_at=datetime.now(UTC),
                            result_summary=ext_fail,
                        )
                    await ext_session.commit()
                    return
                await ext_session.commit()
            await execute_external_ci_run(
                organization_id=organization_id,
                test_run_id=test_run_id,
                contracts=contracts,
                env_info=env_info_fresh,
            )
            return

        if run.execution_source == "agent":
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="VALIDATING",
                updated_at=now,
                result_summary={
                    "dispatch": "deferred",
                    "reason": "agent_worker_not_available_M2",
                    "validated": True,
                },
            )
            await session.commit()
            return

        if env_info["env_type"] != "platform_executor":
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="FAILED",
                updated_at=now,
                result_summary=_fail_summary("unsupported_env_type"),
            )
            await session.commit()
            return

        await repo.update_test_run_status(
            session,
            run=run,
            new_status="RUNNING",
            updated_at=now,
            heartbeat=True,
        )
        await session.commit()

    async with factory() as session:
        run = await repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is None or run.status != "RUNNING":
            await session.commit()
            return
        now = datetime.now(UTC)
        env_info = await execution_query.get_environment_for_start(
            session,
            organization_id=organization_id,
            environment_id=run.env_id,
        )
        if env_info is None:
            await session.commit()
            return
        ok, fail_summary, cases = await _validate_run(session, run=run, env_info=env_info)
        if not ok:
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="FAILED",
                updated_at=now,
                result_summary=fail_summary,
            )
            await session.commit()
            return
        await session.commit()
    await _execute_script_run(
        organization_id=organization_id,
        test_run_id=test_run_id,
        cases=cases,
    )


async def complete_stopping_runs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    now: datetime,
) -> int:
    query = (
        select(TestRun)
        .where(TestRun.status == "STOPPING", TestRun.stop_signal_at.is_not(None))
        .with_for_update()
    )
    if organization_id is not None:
        query = query.where(TestRun.organization_id == organization_id)
    result = await session.execute(query)
    rows = list(result.scalars().all())
    for run in rows:
        run.status = "CANCELLED"
        run.updated_at = now
        run.aggregate_version += 1
    if rows:
        await session.flush()
    return len(rows)


async def complete_stopping_background(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        run = await repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        now = datetime.now(UTC)
        if run is not None:
            await complete_stopping_run(session, run=run, now=now)
        await session.commit()
    await schedule_failure_triage(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    await schedule_gate_evaluation(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
