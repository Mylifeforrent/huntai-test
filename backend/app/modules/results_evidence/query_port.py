"""Cross-module read-only queries for results_evidence."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.models import CaseResult, FailureCluster


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
