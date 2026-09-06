"""Perf subprocess worker (S-M3-01, FR-11): wraps Locust (no in-house engine).

Executes case_type=performance runs through the unified TestRun state machine:
- target whitelist is enforced at acceptance (HT-POL-002, no approval created);
- scenario mutex is enforced by the dispatcher (queued runs stay PENDING);
- high-risk scenarios raise perf_high_risk BEFORE load starts: the run goes
  RUNNING → WAITING_APPROVAL and this worker polls until approval resumes it
  (bound_hash checked by the approval command) or a terminal decision lands;
- kill switch (org capability_controls.tightened_modules contains
  "performance") terminates the load generator within the 60s AC-052 window;
- abort_on_breach stops the load when scenario thresholds are breached;
- load-generator self-monitoring distinguishes "target slow" from
  "load generator saturated" (PRD B.10 gate);
- no automatic retry ever: a crashed worker finalizes FAILED.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psutil

from app.core.db import get_session_factory
from app.modules.quota_governance import command_port as quota_command
from app.modules.results_evidence import object_store
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.command_port import (
    ArtifactWrite,
    CaseResultWrite,
    append_artifact,
    append_case_result,
)
from app.modules.run_orchestration import repository as run_repo

PERF_REPORT_ARTIFACT_KIND = "perf_report"
KILL_SWITCH_MODULE = "performance"
POLL_SECONDS = 5.0
HEARTBEAT_EVERY_POLLS = 3


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _now() -> datetime:
    return datetime.now(UTC)


def _scenario_of(params: dict[str, Any]) -> dict[str, Any]:
    scenario = params.get("perf_scenario")
    return scenario if isinstance(scenario, dict) else {}


def _requests_from_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    steps_raw = case.get("steps")
    steps: list[Any] = steps_raw if isinstance(steps_raw, list) else []
    requests: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        params_raw = step.get("params")
        params: dict[str, Any] = params_raw if isinstance(params_raw, dict) else {}
        if str(step.get("action", "")) != "request":
            continue
        requests.append(
            {
                "method": str(params.get("method", "GET")).upper(),
                "path": str(params.get("path", "/")),
            }
        )
    return requests


LOCUSTFILE_TEMPLATE = """
from locust import HttpUser, constant, task

REQUESTS = {requests!r}


class PerfUser(HttpUser):
    wait_time = constant({wait_seconds!r})

    @task
    def run_steps(self):
        for request in REQUESTS:
            self.client.request(
                request["method"],
                request["path"],
                name=request["path"],
            )
"""


def _write_locustfile(directory: Path, requests: list[dict[str, Any]], wait_seconds: float) -> Path:
    path = directory / "locustfile.py"
    path.write_text(
        LOCUSTFILE_TEMPLATE.format(requests=requests, wait_seconds=wait_seconds),
        encoding="utf-8",
    )
    return path


async def _kill_switch_active(session: Any, *, organization_id: uuid.UUID) -> bool:
    from app.modules.identity_tenancy import query_port as identity_query

    controls = await identity_query.get_capability_controls(
        session, organization_id=organization_id
    )
    modules = controls.get("tightened_modules") if isinstance(controls, dict) else None
    return isinstance(modules, list) and KILL_SWITCH_MODULE in {str(item) for item in modules}


async def _heartbeat(session: Any, *, run: Any) -> None:
    await run_repo.update_test_run_status(
        session,
        run=run,
        new_status="RUNNING",
        updated_at=_now(),
        heartbeat=True,
    )


async def _finalize(
    session: Any,
    *,
    organization_id: uuid.UUID,
    run: Any,
    case: dict[str, Any],
    report: dict[str, Any],
    run_outcome: str,
    created_by: uuid.UUID | None,
) -> None:
    now = _now()
    incomplete = run_outcome not in {"SUCCEEDED", "FAILED"}
    case_result_id = await append_case_result(
        session,
        organization_id=organization_id,
        created_by=created_by,
        created_at=now,
        payload=CaseResultWrite(
            test_run_id=run.id,
            test_case_id=uuid.UUID(str(case["id"])),
            test_case_version_id=None,
            attempt_seq=1,
            outcome=("passed" if run_outcome == "SUCCEEDED" else "failed"),
            is_partial=incomplete,
            normalized_summary={
                "execution_source": "perf",
                "verdict": report.get("verdict"),
            },
        ),
    )
    artifact_id = uuid.uuid4()
    object_key = object_store.generate_object_key(
        organization_id=organization_id,
        artifact_id=artifact_id,
        filename="perf-report.json",
    )
    report_bytes = json.dumps(report, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    checksum = object_store.write_bytes(object_key=object_key, data=report_bytes)
    await append_artifact(
        session,
        organization_id=organization_id,
        created_by=created_by,
        created_at=now,
        payload=ArtifactWrite(
            test_run_id=run.id,
            kind=PERF_REPORT_ARTIFACT_KIND,
            object_key=object_key,
            checksum=checksum,
            case_result_id=case_result_id,
            byte_size=len(report_bytes),
            mime_type="application/json",
            data_classification="Internal",
            original_filename="perf-report.json",
            artifact_id=artifact_id,
        ),
    )
    if run.status == "RUNNING":
        await run_repo.update_test_run_status(
            session,
            run=run,
            new_status=run_outcome,
            updated_at=now,
            result_summary={
                "cases": 1,
                "outcome": run_outcome.lower(),
                "execution_source": "perf",
                "perf": report.get("metrics", {}),
                "clustering": {
                    "generation_status": "skipped",
                    "degraded": False,
                    "unclustered_refs": [],
                },
            },
        )
    elif run.status == "STOPPING":
        await run_repo.update_test_run_status(
            session,
            run=run,
            new_status="CANCELLED",
            updated_at=now,
        )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=created_by,
            action="perf.run.completed",
            resource_type="TestRun",
            resource_id=run.id,
            result="ok" if run_outcome == "SUCCEEDED" else "failed",
        ),
    )


def _iter_stat_entries(payload: Any) -> list[dict[str, Any]]:
    """--json-file yields a list; the live web API yields {"stats": [...]}."""
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("stats"), list):
        return [entry for entry in payload["stats"] if isinstance(entry, dict)]
    return []


def _aggregate_entry(payload: Any) -> dict[str, Any] | None:
    entries = _iter_stat_entries(payload)
    for entry in entries:
        if str(entry.get("name", "")) == "Aggregated":
            return entry
    if not entries:
        return None
    # The final --json list has no Aggregated row: synthesize one.
    total_requests = sum(int(entry.get("num_requests") or 0) for entry in entries)
    total_failures = sum(int(entry.get("num_failures") or 0) for entry in entries)
    histogram: dict[str, int] = {}
    for entry in entries:
        response_times = entry.get("response_times")
        if not isinstance(response_times, dict):
            continue
        for bucket, count in response_times.items():
            histogram[str(bucket)] = histogram.get(str(bucket), 0) + int(count)
    return {
        "num_requests": total_requests,
        "num_failures": total_failures,
        "response_times": histogram,
    }


def _p95_ms(entry: dict[str, Any]) -> float | None:
    percentile = entry.get("response_time_percentile_0.95")
    if isinstance(percentile, (int, float)):
        return float(percentile)
    # Approximate p95 from the response-time histogram buckets.
    histogram = entry.get("response_times")
    if not isinstance(histogram, dict) or not histogram:
        return None
    buckets: list[tuple[int, int]] = []
    for bucket, count in histogram.items():
        try:
            buckets.append((int(float(bucket)), int(count)))
        except (TypeError, ValueError):  # fmt: skip
            continue
    buckets.sort()
    total = sum(count for _, count in buckets)
    if total <= 0:
        return None
    cumulative = 0
    for bucket_ms, count in buckets:
        cumulative += count
        if cumulative >= total * 0.95:
            return float(bucket_ms)
    return float(buckets[-1][0])


def _error_rate_pct(entry: dict[str, Any]) -> float | None:
    num_requests = int(entry.get("num_requests") or 0)
    if num_requests <= 0:
        return None
    fail_ratio = entry.get("fail_ratio")
    if isinstance(fail_ratio, (int, float)) and "fail_ratio" in entry:
        return float(fail_ratio) * 100.0
    num_failures = int(entry.get("num_failures") or 0)
    return num_failures / num_requests * 100.0


async def run_perf_worker(payload: dict[str, Any]) -> None:
    organization_id = uuid.UUID(str(payload["organization_id"]))
    test_run_id = uuid.UUID(str(payload["test_run_id"]))
    created_by_raw = payload.get("created_by")
    created_by = uuid.UUID(str(created_by_raw)) if created_by_raw else None
    cases = [case for case in payload.get("cases", []) if isinstance(case, dict)]
    params = payload.get("params") or {}
    scenario = _scenario_of(params)
    base_url = str(params.get("TARGET_ENV", "")).strip()
    case = cases[0] if cases else {}
    requests = _requests_from_case(case)

    factory = get_session_factory()
    # High-risk approval wait: the run sits in WAITING_APPROVAL until the
    # approval command resumes it (RUNNING) or a decision cancels it.
    async with factory() as session:
        run = await run_repo.get_test_run(
            session, organization_id=organization_id, test_run_id=test_run_id
        )
        awaiting = run is not None and run.status == "WAITING_APPROVAL"
        await session.commit()
    while awaiting:
        await asyncio.sleep(POLL_SECONDS)
        async with factory() as session:
            run = await run_repo.get_test_run(
                session, organization_id=organization_id, test_run_id=test_run_id
            )
            if run is None or run.status != "WAITING_APPROVAL":
                awaiting = False
            await session.commit()
    async with factory() as session:
        run = await run_repo.get_test_run(
            session, organization_id=organization_id, test_run_id=test_run_id
        )
        if run is None or run.status != "RUNNING" or not requests or not base_url:
            await session.commit()
            return
        await session.commit()

    scenario_users = int(scenario.get("users", 1) or 1)
    spawn_rate = float(scenario.get("spawn_rate", 1) or 1)
    run_time_seconds = int(scenario.get("run_time_seconds", 60) or 60)
    wait_seconds = float(scenario.get("wait_seconds", 0.5) or 0.5)
    abort_raw = scenario.get("abort_on_breach")
    abort: dict[str, Any] = abort_raw if isinstance(abort_raw, dict) else {}
    abort_p95_raw = abort.get("max_p95_ms")
    abort_p95 = abort_p95_raw if isinstance(abort_p95_raw, (int, float)) else None
    abort_error_raw = abort.get("max_error_rate")
    abort_error_rate = abort_error_raw if isinstance(abort_error_raw, (int, float)) else None

    with tempfile_directory() as workdir:
        locustfile = _write_locustfile(workdir, requests, wait_seconds)
        port = 18000 + (int(test_run_id.int) % 20000)
        csv_prefix = str(workdir / "stats")
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(locustfile),
            "--autostart",
            "--autoquit",
            "1",
            "--web-port",
            str(port),
            "--web-host",
            "127.0.0.1",
            "-u",
            str(scenario_users),
            "-r",
            str(spawn_rate),
            "--run-time",
            f"{run_time_seconds}s",
            "--host",
            base_url,
            "--only-summary",
            "--json",
            "--skip-log",
            "--csv",
            csv_prefix,
            "--loglevel",
            "ERROR",
            cwd=str(workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        killed_by_kill_switch = False
        aborted_on_breach: str | None = None
        user_cancel = False
        cpu_samples: list[float] = []
        polls = 0
        locust_proc = psutil.Process(proc.pid)
        stats_base = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(timeout=5.0) as monitor_client:
            while proc.returncode is None:
                await asyncio.sleep(POLL_SECONDS)
                polls += 1
                with contextlib.suppress(psutil.Error, OSError):
                    cpu_samples.append(locust_proc.cpu_percent(interval=None))
                async with factory() as session:
                    run = await run_repo.get_test_run(
                        session, organization_id=organization_id, test_run_id=test_run_id
                    )
                    stop = run is None or run.status == "STOPPING" or run.stop_signal_at is not None
                    terminal = run is not None and run.status in {"CANCELLED", "TIMEOUT"}
                    kill = await _kill_switch_active(session, organization_id=organization_id)
                    if (
                        run is not None
                        and run.status == "RUNNING"
                        and polls % HEARTBEAT_EVERY_POLLS == 0
                    ):
                        await _heartbeat(session, run=run)
                    await session.commit()
                if stop:
                    user_cancel = True
                    break
                if terminal:
                    break
                if kill:
                    killed_by_kill_switch = True
                    break
                try:
                    stats_response = await monitor_client.get(f"{stats_base}/stats/requests")
                    stats_payload = (
                        stats_response.json() if stats_response.status_code == 200 else {}
                    )
                except httpx.HTTPError, ValueError:
                    stats_payload = {}
                if abort_p95 is not None or abort_error_rate is not None:
                    live_entry = _aggregate_entry(stats_payload)
                    if live_entry is not None:
                        if abort_p95 is not None:
                            p95 = _p95_ms(live_entry)
                            if p95 is not None and p95 > float(abort_p95):
                                aborted_on_breach = f"max_p95_ms={abort_p95}"
                                break
                        if abort_error_rate is not None:
                            error_rate = _error_rate_pct(live_entry)
                            if error_rate is not None and error_rate > float(abort_error_rate):
                                aborted_on_breach = f"max_error_rate={abort_error_rate}"
                                break
                # Breach/kill must land within the 60s AC-052 window; POLL_SECONDS
                # bounds detection latency well below it.

        stdout_bytes = b""
        if proc.returncode is None:
            proc.terminate()
            try:
                stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except TimeoutError:
                proc.kill()
                stdout_bytes, _ = await proc.communicate()
        else:
            stdout_bytes, _ = await proc.communicate()

        final_stats: Any = []
        raw_output = stdout_bytes.decode("utf-8", errors="replace").strip()
        if raw_output:
            try:
                final_stats = json.loads(raw_output)
            except ValueError:
                final_stats = []
        final_entry = _aggregate_entry(final_stats)
        p95 = _p95_ms(final_entry) if final_entry is not None else None
        error_rate = _error_rate_pct(final_entry) if final_entry is not None else None
        saturated = bool(cpu_samples) and (sum(cpu_samples) / len(cpu_samples)) > 80.0
        report: dict[str, Any] = {
            "metrics": {
                "p95_ms": p95,
                "error_rate": error_rate,
                "total_requests": final_entry.get("num_requests") if final_entry else None,
                "total_failures": final_entry.get("num_failures") if final_entry else None,
                "users": scenario_users,
                "run_time_seconds": run_time_seconds,
            },
            "monitor": {
                "load_gen_cpu_avg": (
                    round(sum(cpu_samples) / len(cpu_samples), 2) if cpu_samples else None
                ),
                "load_gen_saturated": saturated,
                # B.10: distinguish target-slow from load-generator saturation.
                "verdict": "load_gen_saturated" if saturated else "target_measured",
            },
            "scenario": {
                "users": scenario_users,
                "spawn_rate": spawn_rate,
                "run_time_seconds": run_time_seconds,
                "abort_on_breach": abort,
            },
            "aborted_on_breach": aborted_on_breach,
            "killed_by_kill_switch": killed_by_kill_switch,
            "user_cancelled": user_cancel,
        }
        if killed_by_kill_switch:
            run_outcome = "CANCELLED"
            report["verdict"] = "killed_by_kill_switch"
        elif user_cancel:
            run_outcome = "CANCELLED"
            report["verdict"] = "cancelled"
        elif aborted_on_breach is not None:
            run_outcome = "FAILED"
            report["verdict"] = "aborted_on_breach"
        else:
            run_outcome = "SUCCEEDED"
            report["verdict"] = "completed"

        async with factory() as session:
            run = await run_repo.get_test_run(
                session,
                organization_id=organization_id,
                test_run_id=test_run_id,
                for_update=True,
            )
            if run is not None:
                await _finalize(
                    session,
                    organization_id=organization_id,
                    run=run,
                    case=case,
                    report=report,
                    run_outcome=run_outcome,
                    created_by=created_by,
                )
            await session.commit()
        async with factory() as session:
            await quota_command.release_perf_concurrency(session, organization_id=organization_id)
            await session.commit()

        from app.modules.quality_gates.command_port import schedule_gate_evaluation
        from app.modules.run_orchestration.executor import _promote_queued_perf_run

        await schedule_gate_evaluation(
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        scenario_case_id = uuid.UUID(str(case["id"]))
        async with factory() as session:
            await _promote_queued_perf_run(
                session,
                organization_id=organization_id,
                test_case_id=scenario_case_id,
            )


class tempfile_directory:
    """Minimal temp-dir context manager (avoid importing tempfile at module scope)."""

    def __enter__(self) -> Path:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, *args: object) -> None:
        self._tmp.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Perf worker (Locust wrapper, FR-11)")
    parser.add_argument("payload_path", type=str, help="JSON payload file path")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.payload_path).read_text(encoding="utf-8"))
    asyncio.run(run_perf_worker(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
