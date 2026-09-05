"""Playwright subprocess worker for web case execution (S-M2-01)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.modules.results_evidence import object_store
from app.modules.results_evidence.command_port import (
    ArtifactWrite,
    CaseResultWrite,
    StepRunWrite,
    append_artifact,
    append_case_result,
    append_step_run,
)
from app.modules.run_orchestration import repository as run_repo
from app.modules.run_orchestration.variable_resolver import validate_and_resolve_snapshot

# Minimal valid 1x1 PNG
_STUB_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _stub_zip() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("trace.stub", "playwright trace stub")
    return buffer.getvalue()


def _stub_webm() -> bytes:
    return b"\x00\x00\x00\x18ftypwebm\x00\x00\x00\x00webm"


def _is_stub_mode() -> bool:
    return os.environ.get("PLAYWRIGHT_WORKER_STUB", "").lower() in {"1", "true", "yes"}


async def _check_stop_signal(
    session: Any,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> bool:
    run = await run_repo.get_test_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        return True
    return run.status == "STOPPING" or run.stop_signal_at is not None


async def _persist_artifact(
    session: Any,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    test_run_id: uuid.UUID,
    case_result_id: uuid.UUID,
    kind: str,
    filename: str,
    data: bytes,
    mime_type: str,
    data_classification: str = "Confidential",
) -> tuple[uuid.UUID, str]:
    artifact_id = uuid.uuid4()
    object_key = object_store.generate_object_key(
        organization_id=organization_id,
        artifact_id=artifact_id,
        filename=filename,
    )
    checksum = object_store.write_bytes(object_key=object_key, data=data)
    await append_artifact(
        session,
        organization_id=organization_id,
        created_by=created_by,
        created_at=created_at,
        payload=ArtifactWrite(
            artifact_id=artifact_id,
            case_result_id=case_result_id,
            test_run_id=test_run_id,
            kind=kind,
            object_key=object_key,
            checksum=checksum,
            byte_size=len(data),
            mime_type=mime_type,
            data_classification=data_classification,
            original_filename=filename,
        ),
    )
    return artifact_id, object_key


async def _run_stub_case(payload: dict[str, Any]) -> None:
    organization_id = uuid.UUID(str(payload["organization_id"]))
    test_run_id = uuid.UUID(str(payload["test_run_id"]))
    created_by_raw = payload.get("created_by")
    created_by = uuid.UUID(str(created_by_raw)) if created_by_raw else None
    case = payload["case"]
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    steps = case.get("steps", [])
    assertions = case.get("assertions", [])
    resolved_steps, resolved_assertions, errors = validate_and_resolve_snapshot(
        params=params,
        steps=steps,
        assertions=assertions,
    )
    factory = get_session_factory()
    async with factory() as session:
        if await _check_stop_signal(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        ):
            await session.commit()
            return
        now = datetime.now(UTC)
        version_raw = case.get("version_id")
        version_id = uuid.UUID(str(version_raw)) if version_raw else None
        outcome = "failed"
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
                normalized_summary={"reason": "stub_web_failure"},
            ),
        )
        trace_object_key: str | None = None
        _, trace_object_key = await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="trace",
            filename="trace.zip",
            data=_stub_zip(),
            mime_type="application/zip",
        )
        await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="screenshot",
            filename="screenshot.png",
            data=_STUB_PNG,
            mime_type="image/png",
        )
        await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="video",
            filename="video.webm",
            data=_stub_webm(),
            mime_type="video/webm",
        )
        step_index = 0
        if errors:
            await append_step_run(
                session,
                organization_id=organization_id,
                created_by=created_by,
                created_at=now,
                payload=StepRunWrite(
                    case_result_id=case_result_id,
                    step_index=0,
                    action=None,
                    assertion_results={"errors": errors},
                    is_incomplete=True,
                    observation_ref=trace_object_key,
                ),
            )
        else:
            for step in resolved_steps:
                action = step.get("action") if isinstance(step, dict) else None
                action_name = action if isinstance(action, str) else str(action or "unknown")
                known = action_name in {"goto", "click", "fill", "expect"}
                failed = action_name == "click" or not known
                await append_step_run(
                    session,
                    organization_id=organization_id,
                    created_by=created_by,
                    created_at=now,
                    payload=StepRunWrite(
                        case_result_id=case_result_id,
                        step_index=step_index,
                        action=step if isinstance(step, dict) else None,
                        assertion_results={"passed": not failed},
                        is_incomplete=not known,
                        observation_ref=trace_object_key if failed else None,
                    ),
                )
                step_index += 1
                if failed:
                    break
            for assertion in resolved_assertions:
                await append_step_run(
                    session,
                    organization_id=organization_id,
                    created_by=created_by,
                    created_at=now,
                    payload=StepRunWrite(
                        case_result_id=case_result_id,
                        step_index=step_index,
                        action=assertion if isinstance(assertion, dict) else None,
                        assertion_results={"skipped": True},
                        is_incomplete=True,
                    ),
                )
                step_index += 1
        run = await run_repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is not None and run.status == "RUNNING":
            await run_repo.update_test_run_status(
                session,
                run=run,
                new_status="RUNNING",
                updated_at=now,
                heartbeat=True,
            )
        await session.commit()


async def _run_playwright_case(payload: dict[str, Any]) -> None:
    from playwright.async_api import async_playwright

    organization_id = uuid.UUID(str(payload["organization_id"]))
    test_run_id = uuid.UUID(str(payload["test_run_id"]))
    created_by_raw = payload.get("created_by")
    created_by = uuid.UUID(str(created_by_raw)) if created_by_raw else None
    case_raw = payload["case"]
    if not isinstance(case_raw, dict):
        return
    case: dict[str, Any] = case_raw
    params_raw = payload.get("params")
    params = params_raw if isinstance(params_raw, dict) else {}
    base_url = str(params.get("TARGET_ENV", "")).strip()
    steps = case.get("steps", [])
    assertions = case.get("assertions", [])
    resolved_steps, resolved_assertions, errors = validate_and_resolve_snapshot(
        params=params,
        steps=steps,
        assertions=assertions,
    )
    factory = get_session_factory()
    async with factory() as session:
        if await _check_stop_signal(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        ):
            await session.commit()
            return
    if errors:
        async with factory() as session:
            now = datetime.now(UTC)
            version_raw = case.get("version_id")
            version_id = uuid.UUID(str(version_raw)) if version_raw else None
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
                    outcome="failed",
                    normalized_summary={"reason": "variable_unresolved", "details": errors},
                ),
            )
            trace_id, trace_key = await _persist_artifact(
                session,
                organization_id=organization_id,
                created_by=created_by,
                created_at=now,
                test_run_id=test_run_id,
                case_result_id=case_result_id,
                kind="trace",
                filename="trace.zip",
                data=_stub_zip(),
                mime_type="application/zip",
            )
            _ = trace_id
            await append_step_run(
                session,
                organization_id=organization_id,
                created_by=created_by,
                created_at=now,
                payload=StepRunWrite(
                    case_result_id=case_result_id,
                    step_index=0,
                    action=None,
                    assertion_results={"errors": errors},
                    is_incomplete=True,
                    observation_ref=trace_key,
                ),
            )
            await session.commit()
        return

    trace_path = Path(get_settings().artifact_root) / "tmp" / f"{test_run_id}-{uuid.uuid4()}.zip"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    video_dir = trace_path.parent / f"videos-{uuid.uuid4()}"
    video_dir.mkdir(parents=True, exist_ok=True)
    outcome = "passed"
    step_records: list[dict[str, Any]] = []
    trace_object_key: str | None = None

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(record_video_dir=str(video_dir))
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = await context.new_page()
        for step_index, step in enumerate(resolved_steps):
            if not isinstance(step, dict):
                step_records.append(
                    {
                        "step_index": step_index,
                        "action": None,
                        "assertion_results": None,
                        "is_incomplete": True,
                        "failed": True,
                    }
                )
                outcome = "failed"
                break
            action_raw = step.get("action")
            action_name = action_raw if isinstance(action_raw, str) else ""
            params_raw = step.get("params")
            params_step = params_raw if isinstance(params_raw, dict) else {}
            failed = False
            is_incomplete = False
            assertion_results: dict[str, Any] | None = None
            try:
                if action_name == "goto":
                    url = str(params_step.get("url", base_url))
                    await page.goto(url)
                elif action_name == "click":
                    await page.click(str(params_step.get("selector", "")))
                elif action_name == "fill":
                    await page.fill(
                        str(params_step.get("selector", "")),
                        str(params_step.get("value", "")),
                    )
                elif action_name == "expect":
                    is_incomplete = True
                    failed = True
                    outcome = "failed"
                else:
                    failed = True
                    is_incomplete = True
                    outcome = "failed"
            except Exception as exc:  # noqa: BLE001 — step failure must still capture trace
                failed = True
                outcome = "failed"
                assertion_results = {"error": str(exc)}
            step_records.append(
                {
                    "step_index": step_index,
                    "action": step,
                    "assertion_results": assertion_results,
                    "is_incomplete": is_incomplete
                    or action_name
                    not in {
                        "goto",
                        "click",
                        "fill",
                    },
                    "failed": failed,
                }
            )
            if failed:
                break
        screenshot_bytes = await page.screenshot()
        await context.tracing.stop(path=str(trace_path))
        await context.close()
        await browser.close()

    video_files = list(video_dir.glob("*.webm"))
    video_bytes = video_files[0].read_bytes() if video_files else _stub_webm()
    trace_bytes = trace_path.read_bytes() if trace_path.is_file() else _stub_zip()

    async with factory() as session:
        now = datetime.now(UTC)
        version_raw = case.get("version_id")
        version_id = uuid.UUID(str(version_raw)) if version_raw else None
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
            ),
        )
        await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="screenshot",
            filename="screenshot.png",
            data=screenshot_bytes,
            mime_type="image/png",
        )
        await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="video",
            filename="video.webm",
            data=video_bytes,
            mime_type="video/webm",
        )
        _, trace_object_key = await _persist_artifact(
            session,
            organization_id=organization_id,
            created_by=created_by,
            created_at=now,
            test_run_id=test_run_id,
            case_result_id=case_result_id,
            kind="trace",
            filename="trace.zip",
            data=trace_bytes,
            mime_type="application/zip",
        )
        for record in step_records:
            failed = bool(record.get("failed"))
            await append_step_run(
                session,
                organization_id=organization_id,
                created_by=created_by,
                created_at=now,
                payload=StepRunWrite(
                    case_result_id=case_result_id,
                    step_index=int(record["step_index"]),
                    action=record.get("action") if isinstance(record.get("action"), dict) else None,
                    assertion_results=record.get("assertion_results"),
                    is_incomplete=bool(record.get("is_incomplete", False)),
                    observation_ref=trace_object_key if failed else None,
                ),
            )
        _ = resolved_assertions
        run = await run_repo.get_test_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            for_update=True,
        )
        if run is not None and run.status == "RUNNING":
            await run_repo.update_test_run_status(
                session,
                run=run,
                new_status="RUNNING",
                updated_at=now,
                heartbeat=True,
            )
        await session.commit()

    if trace_path.is_file():
        trace_path.unlink(missing_ok=True)
    for video_file in video_dir.glob("*"):
        video_file.unlink(missing_ok=True)
    video_dir.rmdir()


async def run_worker(payload: dict[str, Any]) -> None:
    if _is_stub_mode():
        await _run_stub_case(payload)
    else:
        await _run_playwright_case(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Playwright web case worker")
    parser.add_argument("payload_path", type=str, help="JSON payload file path")
    args = parser.parse_args(argv)
    payload_path = Path(args.payload_path)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    asyncio.run(run_worker(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
