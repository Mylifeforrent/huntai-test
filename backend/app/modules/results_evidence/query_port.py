"""Cross-module read-only queries for results_evidence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.models import CaseResult, FailureCluster


async def get_failure_cluster_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    failure_cluster_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_failure_cluster(
        session,
        organization_id=organization_id,
        failure_cluster_id=failure_cluster_id,
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "test_run_id": row.test_run_id,
        "evidence_refs": list(row.evidence_refs or []),
        "failure_refs": list(row.failure_refs or []),
    }


async def get_case_result_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    case_result_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_case_result(
        session,
        organization_id=organization_id,
        case_result_id=case_result_id,
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "test_run_id": row.test_run_id,
        "test_case_id": row.test_case_id,
    }


async def get_evidence_classifications(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evidence_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    rows = await repo.list_evidence_objects_by_ids(
        session,
        organization_id=organization_id,
        evidence_ids=evidence_ids,
    )
    return {row.id: row.data_classification for row in rows}


async def list_evidence_subject_ids(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evidence_ids: list[uuid.UUID],
) -> list[tuple[uuid.UUID, str, uuid.UUID]]:
    rows = await repo.list_evidence_objects_by_ids(
        session,
        organization_id=organization_id,
        evidence_ids=evidence_ids,
    )
    return [(row.id, row.subject_type, row.subject_id) for row in rows]


def _jira_issue_projection(row: Any) -> dict[str, str] | None:
    source = row.source_object if isinstance(row.source_object, dict) else {}
    if source.get("connector") != "jira":
        return None
    resource = source.get("resource")
    if not isinstance(resource, str) or not resource.strip():
        return None
    external_request_id = source.get("external_request_id")
    payload: dict[str, str] = {"key": resource}
    if isinstance(external_request_id, str) and external_request_id.strip():
        payload["external_request_id"] = external_request_id
    return payload


async def get_latest_jira_issue_for_subject(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
) -> dict[str, str] | None:
    row = await repo.get_latest_jira_evidence_for_subject(
        session,
        organization_id=organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    if row is None:
        return None
    return _jira_issue_projection(row)


async def get_jira_issue_by_external_request_id(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    external_request_id: str,
) -> dict[str, str] | None:
    row = await repo.get_jira_evidence_by_external_request_id(
        session,
        organization_id=organization_id,
        external_request_id=external_request_id,
    )
    if row is None:
        return None
    return _jira_issue_projection(row)


async def get_failure_cluster_confidence(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    failure_cluster_id: uuid.UUID,
) -> float | None:
    row = await repo.get_failure_cluster(
        session,
        organization_id=organization_id,
        failure_cluster_id=failure_cluster_id,
    )
    if row is None:
        return None
    return float(row.confidence)


async def get_evidence_preview_for_test_case(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
) -> dict[str, list[str]]:
    empty: dict[str, list[str]] = {
        "screenshot_artifact_ids": [],
        "video_artifact_ids": [],
        "trace_artifact_ids": [],
    }
    latest = await repo.get_latest_case_result_for_test_case(
        session,
        organization_id=organization_id,
        test_case_id=test_case_id,
    )
    if latest is None:
        return empty
    artifacts = await repo.list_artifacts_for_case_result(
        session,
        organization_id=organization_id,
        case_result_id=latest.id,
    )
    for artifact in artifacts:
        key = f"{artifact.kind}_artifact_ids"
        if key in empty:
            empty[key].append(str(artifact.id))
    return empty


async def get_latest_locator_stale_cluster_for_test_case(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
) -> dict[str, Any] | None:
    case_results = await session.execute(
        select(CaseResult.id).where(
            CaseResult.organization_id == organization_id,
            CaseResult.test_case_id == test_case_id,
        )
    )
    case_result_ids = list(case_results.scalars().all())
    if not case_result_ids:
        return None
    result = await session.execute(
        select(FailureCluster)
        .where(
            FailureCluster.organization_id == organization_id,
            FailureCluster.category == "locator_stale",
            FailureCluster.failure_refs.overlap(case_result_ids),
        )
        .order_by(FailureCluster.created_at.desc(), FailureCluster.id.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": row.id,
        "category": row.category,
        "confidence": float(row.confidence),
        "fixes": list(row.fixes or []),
    }


async def list_case_result_outcomes_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> list[dict[str, Any]]:
    rows = await repo.list_case_results_for_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    return [{"outcome": row.outcome, "is_partial": row.is_partial} for row in rows]
