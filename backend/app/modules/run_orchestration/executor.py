"""Background TestRun orchestration: VALIDATING → execute/cancel → terminal."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.execution_registry import query_port as execution_query
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
            await repo.update_test_run_status(
                session,
                run=run,
                new_status="VALIDATING",
                updated_at=now,
                result_summary={
                    "dispatch": "deferred",
                    "reason": "external_ci_trigger_owned_by_S-M1-05",
                    "validated": True,
                },
            )
            await session.commit()
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
