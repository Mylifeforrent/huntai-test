"""External CI (Jenkins) trigger, poll, and JUnit collection for M1."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.execution_registry import query_port as execution_query
from app.modules.quality_gates.command_port import schedule_gate_evaluation
from app.modules.results_evidence import repository as evidence_repo
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.command_port import (
    CaseResultWrite,
    StepRunWrite,
    append_case_result,
    append_step_run,
    schedule_failure_triage,
)
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.ci_settings import resolve_jenkins_env_ref
from app.modules.run_orchestration.job_schema_validator import validate_params_against_schema
from app.modules.run_orchestration.models import TestRun
from app.modules.test_assets import command_port as test_assets_command
from app.modules.test_assets import query_port as test_assets_query

JENKINS_TIMEOUT = 30.0
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"})


def _fail_summary(reason: str, *, details: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    if details:
        payload["details"] = details
    return payload


async def _complete_stopping_run(
    session: AsyncSession,
    *,
    run: TestRun,
    now: datetime,
) -> None:
    from app.modules.run_orchestration.executor import complete_stopping_run

    await complete_stopping_run(session, run=run, now=now)


def merge_result_summary(
    existing: dict[str, Any] | None,
    *,
    patch: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in patch.items():
        if key == "ci" and isinstance(value, dict):
            ci = dict(merged.get("ci") or {})
            ci.update(value)
            merged["ci"] = ci
        elif key == "clustering" and isinstance(value, dict):
            clustering = dict(merged.get("clustering") or {})
            clustering.update(value)
            merged["clustering"] = clustering
        else:
            merged[key] = value
    return merged


def _ci_summary(run: TestRun) -> dict[str, Any]:
    summary = run.result_summary if isinstance(run.result_summary, dict) else {}
    ci = summary.get("ci")
    return ci if isinstance(ci, dict) else {}


def _artifact_path(contract: dict[str, Any], case: dict[str, Any]) -> str | None:
    job_binding = case.get("job_binding")
    if isinstance(job_binding, dict):
        collect = job_binding.get("collect_config")
        if isinstance(collect, dict):
            path = collect.get("artifact_path")
            if isinstance(path, str) and path.strip():
                return path.strip()
    manifest = contract.get("artifact_manifest")
    if isinstance(manifest, dict):
        path = manifest.get("junit_path") or manifest.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    return "junit.xml"


def _junit_outcome(testcase: ET.Element) -> str:
    if testcase.find("failure") is not None or testcase.find("error") is not None:
        return "failed"
    if testcase.find("skipped") is not None:
        return "incomplete"
    return "passed"


def _should_skip_jenkins_post(ci: dict[str, Any]) -> bool:
    trigger_state = ci.get("trigger_state")
    execution_result = ci.get("execution_result")
    return trigger_state in {"pending", "triggered"} or execution_result == "unknown"


def parse_junit_xml(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    rows: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        name = testcase.get("name") or testcase.get("classname") or "unknown"
        rows.append({"name": str(name), "outcome": _junit_outcome(testcase)})
    return rows


async def validate_external_ci_run(
    session: AsyncSession,
    *,
    run: TestRun,
    env_info: dict[str, Any],
    cases: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None, list[dict[str, Any]]]:
    if env_info.get("env_type") != "external_ci":
        return False, _fail_summary("unsupported_env_type"), []
    if env_info.get("status") != "ACTIVE":
        return False, _fail_summary("env_not_active"), []

    params_raw = run.snapshot.get("params_redacted")
    params = params_raw if isinstance(params_raw, dict) else {}
    contracts: list[dict[str, Any]] = []

    for case in cases:
        binding = case.get("job_binding")
        if not isinstance(binding, dict):
            return False, _fail_summary("missing_job_binding", details=[str(case["id"])]), []
        job_id = binding.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            return False, _fail_summary("missing_job_binding", details=[str(case["id"])]), []

        contract = await execution_query.get_job_contract_for_run(
            session,
            organization_id=run.organization_id,
            environment_id=run.env_id,
            job_id=job_id.strip(),
        )
        if contract is None:
            return (
                False,
                _fail_summary("missing_job_contract", details=[job_id.strip()]),
                [],
            )

        schema_errors = validate_params_against_schema(params, contract.get("params_schema"))
        if schema_errors:
            return (
                False,
                _fail_summary("params_schema_invalid", details=schema_errors),
                [],
            )

        adapter = contract.get("report_adapter")
        if adapter != "junit":
            return False, _fail_summary("adapter_not_in_m1", details=[str(adapter)]), []

        contracts.append({"case": case, "contract": contract, "job_id": job_id.strip()})

    endpoint = env_info.get("endpoint")
    token = resolve_jenkins_env_ref(get_settings(), env_info.get("credential_ref"))
    if not isinstance(endpoint, str) or not endpoint.strip():
        return False, _fail_summary("missing_env_endpoint"), []
    if not token:
        return False, _fail_summary("missing_jenkins_token"), []

    async with httpx.AsyncClient(timeout=JENKINS_TIMEOUT) as client:
        for item in contracts:
            job_id = item["job_id"]
            case = item["case"]
            url = f"{endpoint.rstrip('/')}/job/{job_id}/api/json"
            try:
                response = await client.get(url, auth=("", token))
            except httpx.TimeoutException:
                return False, _fail_summary("jenkins_unreachable"), []
            except httpx.HTTPError:
                return False, _fail_summary("jenkins_unreachable"), []

            if response.status_code == 404:
                await test_assets_command.invalidate_case_for_missing_job(
                    session,
                    organization_id=run.organization_id,
                    test_case_id=uuid.UUID(str(case["id"])),
                    actor_user_id=run.created_by,
                    job_id=job_id,
                )
                await append_audit_event(
                    session,
                    AuditAppendInput(
                        organization_id=run.organization_id,
                        actor_user_id=run.created_by,
                        action="test_case.invalidated",
                        resource_type="test_case",
                        resource_id=uuid.UUID(str(case["id"])),
                        project_id=run.project_id,
                        result="ok",
                        request_hash=None,
                    ),
                )
                return False, _fail_summary("jenkins_job_not_found", details=[job_id]), []
            if response.status_code >= 500:
                return False, _fail_summary("jenkins_unreachable"), []
            if response.status_code >= 400:
                return False, _fail_summary("jenkins_job_check_failed", details=[job_id]), []

    return True, None, contracts


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


async def _persist_ci(
    session: AsyncSession,
    *,
    run: TestRun,
    ci_patch: dict[str, Any],
    new_status: str | None = None,
    now: datetime | None = None,
    heartbeat: bool = False,
) -> TestRun:
    effective_now = now or datetime.now(UTC)
    existing_summary = run.result_summary if isinstance(run.result_summary, dict) else None
    summary = merge_result_summary(existing_summary, patch={"ci": ci_patch})
    if new_status is None:
        run.result_summary = summary
        run.updated_at = effective_now
        run.aggregate_version += 1
        if heartbeat:
            run.last_heartbeat_at = effective_now
        await session.flush()
        return run
    return await repo.update_test_run_status(
        session,
        run=run,
        new_status=new_status,
        updated_at=effective_now,
        result_summary=summary,
        heartbeat=heartbeat,
    )


async def _trigger_jenkins(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    job_id: str,
    token: str,
    params: dict[str, Any],
) -> tuple[str | None, int | None, str | None]:
    base = endpoint.rstrip("/")
    if params:
        url = f"{base}/job/{job_id}/buildWithParameters"
        response = await client.post(url, auth=("", token), params=params)
    else:
        url = f"{base}/job/{job_id}/build"
        response = await client.post(url, auth=("", token))
    if response.status_code >= 500 or response.status_code == 408:
        return None, None, "unknown"
    if response.status_code not in {200, 201, 202, 302}:
        return None, None, "failed"
    queue_url = response.headers.get("Location")
    return queue_url, None, None


async def _resolve_build_number(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    token: str,
    queue_url: str | None,
    job_id: str,
    ci: dict[str, Any],
) -> int | None:
    if ci.get("build_number") is not None:
        try:
            return int(ci["build_number"])
        except (TypeError, ValueError):  # fmt: skip
            pass
    if queue_url:
        api_url = urljoin(queue_url.rstrip("/") + "/", "api/json")
        try:
            response = await client.get(api_url, auth=("", token))
            if response.status_code == 200:
                payload = response.json()
                executable = payload.get("executable")
                if isinstance(executable, dict) and executable.get("number") is not None:
                    return int(executable["number"])
        except (httpx.HTTPError, TypeError, ValueError):  # fmt: skip
            pass
    base = endpoint.rstrip("/")
    job_url = f"{base}/job/{job_id}/lastBuild/api/json"
    try:
        response = await client.get(job_url, auth=("", token))
        if response.status_code == 200:
            payload = response.json()
            number = payload.get("number")
            if number is not None:
                return int(number)
    except (httpx.HTTPError, TypeError, ValueError):  # fmt: skip
        return None
    return None


async def _build_finished(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    token: str,
    job_id: str,
    build_number: int,
) -> tuple[bool, str | None]:
    url = f"{endpoint.rstrip('/')}/job/{job_id}/{build_number}/api/json"
    try:
        response = await client.get(url, auth=("", token))
    except httpx.HTTPError:
        return False, None
    if response.status_code != 200:
        return False, None
    payload = response.json()
    building = payload.get("building")
    result = payload.get("result")
    if building is True:
        return False, None
    if isinstance(result, str):
        return True, result
    return True, None


async def _fetch_junit_artifact(
    client: httpx.AsyncClient,
    *,
    endpoint: str,
    token: str,
    job_id: str,
    build_number: int,
    artifact_path: str,
) -> str | None:
    url = f"{endpoint.rstrip('/')}/job/{job_id}/{build_number}/artifact/{artifact_path.lstrip('/')}"
    try:
        response = await client.get(url, auth=("", token))
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response.text


async def _write_junit_results(
    session: AsyncSession,
    *,
    run: TestRun,
    cases: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    junit_rows: list[dict[str, str]],
    xml_text: str,
    now: datetime,
) -> bool:
    all_passed = True
    created_by = run.created_by
    checksum = hashlib.sha256(xml_text.encode("utf-8")).hexdigest()
    claim = f"junit report checksum={checksum[:16]} cases={len(junit_rows)}"
    content_ref = f"junit://{run.id}/{checksum[:16]}"

    if len(cases) == 1:
        mapped = [(cases[0], junit_rows)]
    else:
        mapped = [(case_item["case"], junit_rows) for case_item in contracts]

    for case, rows in mapped:
        if not rows:
            rows = [{"name": "empty", "outcome": "failed"}]
        version_raw = case.get("version_id")
        version_id = uuid.UUID(str(version_raw)) if version_raw else None
        worst = "passed"
        for row in rows:
            outcome = row["outcome"]
            if outcome == "failed":
                worst = "failed"
            elif outcome == "incomplete" and worst == "passed":
                worst = "incomplete"
        if worst != "passed":
            all_passed = False
        case_result_id = await append_case_result(
            session,
            organization_id=run.organization_id,
            created_by=created_by,
            created_at=now,
            payload=CaseResultWrite(
                test_run_id=run.id,
                test_case_id=uuid.UUID(str(case["id"])),
                test_case_version_id=version_id,
                attempt_seq=1,
                outcome=worst,
                normalized_summary={"junit_cases": len(rows)},
            ),
        )
        await append_step_run(
            session,
            organization_id=run.organization_id,
            created_by=created_by,
            created_at=now,
            payload=StepRunWrite(
                case_result_id=case_result_id,
                step_index=0,
                action={"type": "external_ci", "source": "junit"},
                assertion_results={"items": rows[:20]},
                is_incomplete=False,
            ),
        )
        await evidence_repo.insert_evidence_object(
            session,
            organization_id=run.organization_id,
            created_at=now,
            created_by=created_by,
            claim=claim[:500],
            source_object={
                "connector": "external_ci",
                "resource": str(case_result_id),
                "adapter": "junit",
                "timestamp": now.isoformat(),
            },
            content_ref=content_ref,
            subject_type="case_result",
            subject_id=case_result_id,
            data_classification="Internal",
        )
    return all_passed


async def _finalize_terminal(
    session: AsyncSession,
    *,
    run: TestRun,
    all_passed: bool,
    now: datetime,
    extra_summary: dict[str, Any] | None = None,
    cancel_mode: bool = False,
) -> None:
    final_status = "CANCELLED" if cancel_mode else ("SUCCEEDED" if all_passed else "FAILED")
    summary = merge_result_summary(
        run.result_summary if isinstance(run.result_summary, dict) else None,
        patch={
            "ci": {"collect_state": "done"},
            "cases": len(run.snapshot.get("case_ids", [])),
            "outcome": final_status.lower(),
            "clustering": {
                "generation_status": "pending",
                "degraded": False,
                "unclustered_refs": [],
            },
        },
    )
    if extra_summary:
        summary.update(extra_summary)
    await repo.update_test_run_status(
        session,
        run=run,
        new_status=final_status,
        updated_at=now,
        result_summary=summary,
    )


async def collect_junit_for_run(
    session: AsyncSession,
    *,
    run: TestRun,
    contracts: list[dict[str, Any]],
    env_info: dict[str, Any],
    client: httpx.AsyncClient,
    token: str,
    endpoint: str,
    ci: dict[str, Any],
    cancel_mode: bool = False,
) -> bool:
    build_number = ci.get("build_number")
    if build_number is None:
        return False
    try:
        build_num = int(build_number)
    except (TypeError, ValueError):  # fmt: skip
        return False

    case_rows = [item["case"] for item in contracts]
    artifact_path = _artifact_path(contracts[0]["contract"], contracts[0]["case"])
    xml_text = await _fetch_junit_artifact(
        client,
        endpoint=endpoint,
        token=token,
        job_id=str(ci.get("job_id", contracts[0]["job_id"])),
        build_number=build_num,
        artifact_path=artifact_path or "junit.xml",
    )
    now = datetime.now(UTC)
    if xml_text is None:
        fail_status = "CANCELLED" if cancel_mode else "FAILED"
        await repo.update_test_run_status(
            session,
            run=run,
            new_status=fail_status,
            updated_at=now,
            result_summary=merge_result_summary(
                run.result_summary if isinstance(run.result_summary, dict) else None,
                patch={"ci": {"collect_state": "failed", "reason": "artifact_fetch_failed"}},
            ),
        )
        return True

    junit_rows = parse_junit_xml(xml_text)
    all_passed = await _write_junit_results(
        session,
        run=run,
        cases=case_rows,
        contracts=contracts,
        junit_rows=junit_rows,
        xml_text=xml_text,
        now=now,
    )
    await _finalize_terminal(
        session,
        run=run,
        all_passed=all_passed,
        now=now,
        cancel_mode=cancel_mode,
    )
    return True


async def execute_external_ci_run(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    contracts: list[dict[str, Any]],
    env_info: dict[str, Any],
) -> None:
    factory = get_session_factory()
    settings = get_settings()
    endpoint = str(env_info.get("endpoint", "")).strip()
    token = resolve_jenkins_env_ref(settings, env_info.get("credential_ref"))
    if not endpoint or not token:
        async with factory() as session:
            run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
            if run is not None and run.status == "VALIDATING":
                await repo.update_test_run_status(
                    session,
                    run=run,
                    new_status="FAILED",
                    updated_at=datetime.now(UTC),
                    result_summary=_fail_summary("missing_jenkins_config"),
                )
            await session.commit()
        return

    params_raw: dict[str, Any] = {}
    skip_post = False
    job_id = contracts[0]["job_id"]
    trigger_fingerprint: str | None = None

    async with factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        now = datetime.now(UTC)
        if run is None or run.status not in {"VALIDATING", "WAITING_EXTERNAL", "RUNNING"}:
            await session.commit()
            return
        if run.stop_signal_at is not None:
            await _complete_stopping_run(session, run=run, now=now)
            await session.commit()
            return
        snapshot_params = run.snapshot.get("params_redacted")
        if isinstance(snapshot_params, dict):
            params_raw = dict(snapshot_params)
        ci = _ci_summary(run)
        skip_post = _should_skip_jenkins_post(ci)
        trigger_fingerprint = run.idempotency_key
        if not skip_post:
            await _persist_ci(
                session,
                run=run,
                ci_patch={
                    "trigger_state": "pending",
                    "trigger_fingerprint": trigger_fingerprint,
                    "job_id": job_id,
                },
                new_status="WAITING_EXTERNAL",
                now=now,
            )
        await session.commit()

    async with httpx.AsyncClient(timeout=JENKINS_TIMEOUT) as client:
        if not skip_post:
            queue_url: str | None = None
            build_number: int | None = None
            trigger_error: str | None = None
            try:
                queue_url, build_number, trigger_error = await _trigger_jenkins(
                    client,
                    endpoint=endpoint,
                    job_id=job_id,
                    token=token,
                    params=params_raw,
                )
            except httpx.TimeoutException:
                trigger_error = "unknown"
            except httpx.HTTPError:
                trigger_error = "unknown"

            async with factory() as session:
                run = await _load_run(
                    session,
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                )
                now = datetime.now(UTC)
                if run is None:
                    await session.commit()
                    return
                if run.stop_signal_at is not None:
                    await _complete_stopping_run(session, run=run, now=now)
                    await session.commit()
                    return

                if trigger_error == "unknown":
                    await _persist_ci(
                        session,
                        run=run,
                        ci_patch={
                            "trigger_state": "pending",
                            "execution_result": "unknown",
                            "job_id": job_id,
                        },
                        new_status="WAITING_EXTERNAL",
                        now=now,
                    )
                    await session.commit()
                    return
                if trigger_error == "failed" or queue_url is None:
                    await repo.update_test_run_status(
                        session,
                        run=run,
                        new_status="FAILED",
                        updated_at=now,
                        result_summary=_fail_summary("jenkins_trigger_failed"),
                    )
                    await session.commit()
                    return

                ci_patch: dict[str, Any] = {
                    "trigger_state": "triggered",
                    "trigger_fingerprint": trigger_fingerprint,
                    "job_id": job_id,
                    "queue_url": queue_url,
                }
                if build_number is not None:
                    ci_patch["build_number"] = build_number
                await _persist_ci(
                    session,
                    run=run,
                    ci_patch=ci_patch,
                    new_status="WAITING_EXTERNAL",
                    now=now,
                )
                await session.commit()

        async with factory() as session:
            run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
            now = datetime.now(UTC)
            if run is None or run.status in TERMINAL_STATUSES:
                await session.commit()
                return
            if run.stop_signal_at is not None:
                await _complete_stopping_run(session, run=run, now=now)
                await session.commit()
                return
            ci = _ci_summary(run)
            if ci.get("execution_result") == "unknown" and run.status == "WAITING_EXTERNAL":
                await session.commit()
                return
            if ci.get("collect_state") == "done":
                await session.commit()
                return
            await session.commit()

        async with factory() as session:
            run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
            now = datetime.now(UTC)
            if run is None:
                await session.commit()
                return
            ci = _ci_summary(run)
            build_number = await _resolve_build_number(
                client,
                endpoint=endpoint,
                token=token,
                queue_url=ci.get("queue_url") if isinstance(ci.get("queue_url"), str) else None,
                job_id=job_id,
                ci=ci,
            )
            if build_number is not None and run.status == "WAITING_EXTERNAL":
                await _persist_ci(
                    session,
                    run=run,
                    ci_patch={"build_number": build_number},
                    new_status="RUNNING",
                    now=now,
                    heartbeat=True,
                )
            await session.commit()

        finished = False
        build_result: str | None = None
        for _ in range(5):
            async with factory() as session:
                run = await _load_run(
                    session,
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                )
                if run is None or run.status in TERMINAL_STATUSES:
                    await session.commit()
                    return
                ci = _ci_summary(run)
                build_number_raw = ci.get("build_number")
                if build_number_raw is None:
                    await session.commit()
                    break
                try:
                    build_num = int(build_number_raw)
                except (TypeError, ValueError):  # fmt: skip
                    await session.commit()
                    break
                finished, build_result = await _build_finished(
                    client,
                    endpoint=endpoint,
                    token=token,
                    job_id=job_id,
                    build_number=build_num,
                )
                await session.commit()
                if finished:
                    break
                await asyncio.sleep(0.05)

        async with factory() as session:
            run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
            now = datetime.now(UTC)
            if run is None or run.status in TERMINAL_STATUSES:
                await session.commit()
                return
            if not finished:
                await session.commit()
                return
            ci = _ci_summary(run)
            collected = await collect_junit_for_run(
                session,
                run=run,
                contracts=contracts,
                env_info=env_info,
                client=client,
                token=token,
                endpoint=endpoint,
                ci=ci,
            )
            if collected and build_result == "FAILURE":
                run = await _load_run(
                    session,
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                )
                if run is not None and run.status == "SUCCEEDED":
                    await repo.update_test_run_status(
                        session,
                        run=run,
                        new_status="FAILED",
                        updated_at=now,
                        result_summary=merge_result_summary(
                            run.result_summary if isinstance(run.result_summary, dict) else None,
                            patch={"outcome": "failed"},
                        ),
                    )
            await session.commit()

    await schedule_failure_triage(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    await schedule_gate_evaluation(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )


async def _contracts_for_run(
    session: AsyncSession,
    *,
    run: TestRun,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    env_info = await execution_query.get_environment_for_run(
        session,
        organization_id=run.organization_id,
        environment_id=run.env_id,
    )
    case_ids_raw = run.snapshot.get("case_ids", [])
    if not isinstance(case_ids_raw, list):
        return [], env_info
    case_ids = [uuid.UUID(str(cid)) for cid in case_ids_raw]
    cases = await test_assets_query.get_cases_for_run_validation(
        session,
        organization_id=run.organization_id,
        project_id=run.project_id,
        case_ids=case_ids,
    )
    contracts: list[dict[str, Any]] = []
    for case in cases:
        binding = case.get("job_binding")
        if not isinstance(binding, dict):
            continue
        job_id = binding.get("job_id")
        if not isinstance(job_id, str):
            continue
        contract = await execution_query.get_job_contract_for_run(
            session,
            organization_id=run.organization_id,
            environment_id=run.env_id,
            job_id=job_id.strip(),
        )
        if contract is None:
            continue
        contracts.append({"case": case, "contract": contract, "job_id": job_id.strip()})
    return contracts, env_info


async def resume_external_ci_run(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        if run is None:
            await session.commit()
            return
        contracts, env_info = await _contracts_for_run(session, run=run)
        await session.commit()
    if env_info is None or not contracts:
        return
    await execute_external_ci_run(
        organization_id=organization_id,
        test_run_id=test_run_id,
        contracts=contracts,
        env_info=env_info,
    )


async def best_effort_collect_on_cancel(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    settings = get_settings()
    async with factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        if run is None:
            await session.commit()
            return
        ci = _ci_summary(run)
        if ci.get("trigger_state") != "triggered":
            await session.commit()
            return
        contracts, env_info = await _contracts_for_run(session, run=run)
        await session.commit()

    if env_info is None:
        return
    endpoint = str(env_info.get("endpoint", "")).strip()
    token = resolve_jenkins_env_ref(settings, env_info.get("credential_ref"))
    if not endpoint or not token or not contracts:
        return

    async with httpx.AsyncClient(timeout=JENKINS_TIMEOUT) as client, factory() as session:
        run = await _load_run(session, organization_id=organization_id, test_run_id=test_run_id)
        if run is None:
            await session.commit()
            return
        if run.status in TERMINAL_STATUSES and run.status != "CANCELLED":
            await session.commit()
            return
        ci = _ci_summary(run)
        await collect_junit_for_run(
            session,
            run=run,
            contracts=contracts,
            env_info=env_info,
            client=client,
            token=token,
            endpoint=endpoint,
            ci=ci,
            cancel_mode=True,
        )
        await session.commit()

    await schedule_failure_triage(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    await schedule_gate_evaluation(
        organization_id=organization_id,
        test_run_id=test_run_id,
    )


def parse_ci_observation_payload(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):  # fmt: skip
        return None
    if not isinstance(payload, dict):
        return None
    build = payload.get("build")
    if not isinstance(build, dict):
        return None
    parsed: dict[str, Any] = {}
    if build.get("number") is not None:
        try:
            parsed["build_number"] = int(build["number"])
        except (TypeError, ValueError):  # fmt: skip
            return None
    phase = build.get("phase")
    if isinstance(phase, str):
        parsed["phase"] = phase
    status = build.get("status")
    if isinstance(status, str):
        parsed["status"] = status
    job = payload.get("job") or build.get("job")
    if isinstance(job, dict) and isinstance(job.get("name"), str):
        parsed["job_id"] = job["name"]
    elif isinstance(payload.get("name"), str):
        parsed["job_id"] = payload["name"]
    if "job_id" not in parsed:
        return None
    return parsed
