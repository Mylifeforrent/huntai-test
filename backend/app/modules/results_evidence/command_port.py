"""Cross-module commands for failure triage and case results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.a2_service import confidence_to_decimal, run_a2_triage
from app.modules.results_evidence.a3_service import run_a3_for_locator_cluster
from app.modules.run_orchestration import command_port as run_command
from app.modules.run_orchestration import query_port as run_query

TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"})


@dataclass(frozen=True)
class CaseResultWrite:
    test_run_id: uuid.UUID
    test_case_id: uuid.UUID
    test_case_version_id: uuid.UUID | None
    attempt_seq: int
    outcome: str
    is_late: bool = False
    is_partial: bool = False
    chunk_key: str | None = None
    normalized_summary: dict[str, Any] | None = None
    data_classification: str = "Internal"


@dataclass(frozen=True)
class StepRunWrite:
    case_result_id: uuid.UUID
    step_index: int
    action: dict[str, Any] | None
    assertion_results: dict[str, Any] | list[dict[str, Any]] | None
    is_incomplete: bool
    observation_ref: str | None = None
    token_usage: dict[str, Any] | None = None


@dataclass(frozen=True)
class ArtifactWrite:
    test_run_id: uuid.UUID
    kind: str
    object_key: str
    checksum: str
    case_result_id: uuid.UUID | None = None
    byte_size: int | None = None
    mime_type: str | None = None
    data_classification: str = "Confidential"
    original_filename: str | None = None
    artifact_id: uuid.UUID | None = None


async def append_case_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    payload: CaseResultWrite,
) -> uuid.UUID:
    row = await repo.insert_case_result(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        test_run_id=payload.test_run_id,
        test_case_id=payload.test_case_id,
        test_case_version_id=payload.test_case_version_id,
        attempt_seq=payload.attempt_seq,
        outcome=payload.outcome,
        is_late=payload.is_late,
        is_partial=payload.is_partial,
        chunk_key=payload.chunk_key,
        normalized_summary=payload.normalized_summary,
        data_classification=payload.data_classification,
    )
    return row.id


async def append_artifact(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    payload: ArtifactWrite,
) -> uuid.UUID:
    row = await repo.insert_artifact(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        case_result_id=payload.case_result_id,
        test_run_id=payload.test_run_id,
        kind=payload.kind,
        object_key=payload.object_key,
        checksum=payload.checksum,
        byte_size=payload.byte_size,
        mime_type=payload.mime_type,
        data_classification=payload.data_classification,
        original_filename=payload.original_filename,
        artifact_id=payload.artifact_id,
    )
    return row.id


async def append_step_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    payload: StepRunWrite,
) -> uuid.UUID:
    assertion_payload: dict[str, Any] | None
    if isinstance(payload.assertion_results, list):
        assertion_payload = {"items": payload.assertion_results}
    else:
        assertion_payload = payload.assertion_results
    row = await repo.insert_step_run(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        case_result_id=payload.case_result_id,
        step_index=payload.step_index,
        action=payload.action,
        observation_ref=payload.observation_ref,
        assertion_results=assertion_payload,
        token_usage=payload.token_usage,
        is_incomplete=payload.is_incomplete,
    )
    return row.id


async def mark_case_result_partial(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    case_result_id: uuid.UUID,
) -> bool:
    return await repo.mark_case_result_partial(
        session,
        organization_id=organization_id,
        case_result_id=case_result_id,
    )


async def find_case_result_id_by_attempt(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    test_case_id: uuid.UUID,
    attempt_seq: int,
) -> uuid.UUID | None:
    row = await repo.get_case_result_by_attempt(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        test_case_id=test_case_id,
        attempt_seq=attempt_seq,
    )
    return None if row is None else row.id


async def artifact_object_key_exists(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    object_key: str,
) -> bool:
    return await repo.artifact_key_exists(
        session,
        organization_id=organization_id,
        object_key=object_key,
    )


async def append_ci_report_evidence(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    claim: str,
    source_object: dict[str, Any],
    content_ref: str,
    subject_id: uuid.UUID,
) -> uuid.UUID:
    row = await repo.insert_evidence_object(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        claim=claim,
        source_object=source_object,
        content_ref=content_ref,
        subject_type="case_result",
        subject_id=subject_id,
        data_classification="Internal",
    )
    return row.id


def _clustering_state(result_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result_summary:
        return None
    clustering = result_summary.get("clustering")
    if isinstance(clustering, dict):
        return clustering
    return None


async def _build_failed_case_payloads(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    failed_rows: list[Any],
) -> list[dict[str, Any]]:
    case_result_ids = [row.id for row in failed_rows]
    step_rows = await repo.list_step_runs_for_case_results(
        session,
        organization_id=organization_id,
        case_result_ids=case_result_ids,
    )
    steps_by_case: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for step in step_rows:
        steps_by_case.setdefault(step.case_result_id, []).append(
            {
                "step_index": step.step_index,
                "observation_ref": step.observation_ref,
                "assertion_results": step.assertion_results,
                "is_incomplete": step.is_incomplete,
                "action": step.action,
            }
        )
    payloads: list[dict[str, Any]] = []
    for row in failed_rows:
        summary = row.normalized_summary if isinstance(row.normalized_summary, dict) else {}
        action = row.action if hasattr(row, "action") else None
        _ = action
        step_assertions = steps_by_case.get(row.id, [])
        if step_assertions and isinstance(summary, dict) and "path" not in summary:
            first_action = step_assertions[0].get("action")
            if isinstance(first_action, dict):
                params = first_action.get("params")
                if isinstance(params, dict) and isinstance(params.get("path"), str):
                    summary = {**summary, "path": params["path"]}
        payloads.append(
            {
                "id": row.id,
                "test_case_id": row.test_case_id,
                "normalized_summary": summary,
                "step_assertions": step_assertions,
            }
        )
    return payloads


async def _create_evidence_pool_for_failed_cases(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    failed_rows: list[Any],
    now: datetime,
) -> dict[uuid.UUID, uuid.UUID]:
    case_result_ids = [row.id for row in failed_rows]
    step_rows = await repo.list_step_runs_for_case_results(
        session,
        organization_id=organization_id,
        case_result_ids=case_result_ids,
    )
    steps_by_case: dict[uuid.UUID, list[Any]] = {}
    for step in step_rows:
        steps_by_case.setdefault(step.case_result_id, []).append(step)
    existing_rows = await repo.list_evidence_objects_for_subjects(
        session,
        organization_id=organization_id,
        subject_type="case_result",
        subject_ids=case_result_ids,
    )
    evidence_by_case: dict[uuid.UUID, uuid.UUID] = {}
    for existing in existing_rows:
        evidence_by_case.setdefault(existing.subject_id, existing.id)
    for row in failed_rows:
        if row.id in evidence_by_case:
            continue
        summary = row.normalized_summary if isinstance(row.normalized_summary, dict) else {}
        status_code = summary.get("status_code")
        claim_parts = ["failed case result"]
        if isinstance(status_code, int):
            claim_parts.append(f"status_code={status_code}")
        claim = " ".join(claim_parts)
        content_ref: str | None = None
        for step in steps_by_case.get(row.id, []):
            if step.observation_ref:
                content_ref = step.observation_ref
                break
        evidence = await repo.insert_evidence_object(
            session,
            organization_id=organization_id,
            created_at=now,
            created_by=created_by,
            claim=claim,
            source_object={
                "connector": "platform_executor",
                "resource": str(row.id),
                "version": str(row.attempt_seq),
                "timestamp": now.isoformat(),
            },
            content_ref=content_ref,
            subject_type="case_result",
            subject_id=row.id,
            data_classification="Internal",
        )
        evidence_by_case[row.id] = evidence.id
    return evidence_by_case


async def append_jira_issue_evidence(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    subject_type: str,
    subject_id: uuid.UUID,
    issue_key: str,
    external_request_id: str,
    evidence_ids: list[uuid.UUID],
    approval_id: uuid.UUID,
    bound_hash: str,
) -> uuid.UUID:
    claim_parts = [f"Jira defect {issue_key}"]
    if evidence_ids:
        claim_parts.append(f"evidence_refs={len(evidence_ids)}")
    row = await repo.insert_evidence_object(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        claim=" ".join(claim_parts),
        source_object={
            "connector": "jira",
            "resource": issue_key,
            "version": "1",
            "timestamp": created_at.isoformat(),
            "external_request_id": external_request_id,
            "approval_id": str(approval_id),
            "bound_hash": bound_hash,
            "evidence_ids": [str(item) for item in evidence_ids],
        },
        content_ref=None,
        subject_type=subject_type,
        subject_id=subject_id,
        data_classification="Internal",
    )
    return row.id


def _merge_cluster_evidence_refs(
    draft_evidence_refs: list[uuid.UUID],
    failure_refs: list[uuid.UUID],
    evidence_by_case: dict[uuid.UUID, uuid.UUID],
) -> list[uuid.UUID]:
    extra_refs = [evidence_by_case[ref] for ref in failure_refs if ref in evidence_by_case]
    merged: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for ref in [*draft_evidence_refs, *extra_refs]:
        if ref not in seen:
            seen.add(ref)
            merged.append(ref)
    return merged


async def prepare_failure_triage(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> bool:
    """Set clustering projection and return whether background triage should run."""
    run = await run_query.get_run_clustering_context(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if run is None or run["status"] not in TERMINAL_STATUSES:
        return False
    existing = _clustering_state(run["result_summary"])
    if existing is not None:
        status = str(existing.get("generation_status", ""))
        if status in {"ready", "degraded"}:
            return False
    failed_rows = await repo.list_failed_case_results_for_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if not failed_rows:
        await run_command.merge_clustering_projection(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            clustering={
                "generation_status": "ready",
                "degraded": False,
                "unclustered_refs": [],
            },
        )
        return False
    if await repo.count_failure_clusters_for_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    ):
        return False
    await run_command.merge_clustering_projection(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
        clustering={
            "generation_status": "pending",
            "degraded": False,
            "unclustered_refs": [],
        },
    )
    return True


async def run_failure_triage_background(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        run = await run_query.get_run_clustering_context(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        if run is None:
            await session.commit()
            return
        existing = _clustering_state(run["result_summary"])
        if existing is not None and str(existing.get("generation_status")) in {"ready", "degraded"}:
            await session.commit()
            return
        if await repo.count_failure_clusters_for_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        ):
            await session.commit()
            return
        failed_rows = await repo.list_failed_case_results_for_run(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        if not failed_rows:
            await run_command.merge_clustering_projection(
                session,
                organization_id=organization_id,
                test_run_id=test_run_id,
                clustering={
                    "generation_status": "ready",
                    "degraded": False,
                    "unclustered_refs": [],
                },
            )
            await session.commit()
            return
        failed_payloads = await _build_failed_case_payloads(
            session,
            organization_id=organization_id,
            failed_rows=failed_rows,
        )
        now = datetime.now(UTC)
        evidence_by_case = await _create_evidence_pool_for_failed_cases(
            session,
            organization_id=organization_id,
            created_by=run["created_by"],
            failed_rows=failed_rows,
            now=now,
        )
        triage = await run_a2_triage(
            session,
            organization_id=organization_id,
            user_id=run["created_by"],
            failed_cases=failed_payloads,
            evidence_pool=set(evidence_by_case.values()),
        )
        failed_by_id = {item["id"]: item for item in failed_payloads}
        case_result_test_case_ids = {row.id: row.test_case_id for row in failed_rows}
        for draft in triage.clusters:
            fixes = list(draft.fixes)
            if draft.category == "locator_stale":
                a3_fixes = await run_a3_for_locator_cluster(
                    session,
                    organization_id=organization_id,
                    user_id=run["created_by"],
                    failure_refs=draft.failure_refs,
                    failed_payloads=failed_by_id,
                    case_result_test_case_ids=case_result_test_case_ids,
                )
                fixes.extend(a3_fixes)
            await repo.insert_failure_cluster(
                session,
                organization_id=organization_id,
                created_at=now,
                created_by=run["created_by"],
                test_run_id=test_run_id,
                category=draft.category,
                root_cause=draft.root_cause,
                confidence=float(confidence_to_decimal(draft.confidence)),
                blocking_judgment=draft.blocking_judgment,
                evidence_refs=_merge_cluster_evidence_refs(
                    draft.evidence_refs,
                    draft.failure_refs,
                    evidence_by_case,
                ),
                failure_refs=draft.failure_refs,
                unclustered_refs=triage.unclustered_refs or None,
                fixes=fixes or None,
            )
        await run_command.merge_clustering_projection(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
            clustering={
                "generation_status": triage.generation_status,
                "degraded": triage.degraded,
                "unclustered_refs": [str(item) for item in triage.unclustered_refs],
            },
        )
        await session.commit()


async def schedule_failure_triage(
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        should_run = await prepare_failure_triage(
            session,
            organization_id=organization_id,
            test_run_id=test_run_id,
        )
        await session.commit()
    if should_run:
        await run_failure_triage_background(
            organization_id=organization_id,
            test_run_id=test_run_id,
        )


__all__ = [
    "ArtifactWrite",
    "CaseResultWrite",
    "StepRunWrite",
    "append_artifact",
    "append_case_result",
    "append_ci_report_evidence",
    "append_jira_issue_evidence",
    "append_step_run",
    "artifact_object_key_exists",
    "find_case_result_id_by_attempt",
    "mark_case_result_partial",
    "prepare_failure_triage",
    "run_failure_triage_background",
    "schedule_failure_triage",
]
