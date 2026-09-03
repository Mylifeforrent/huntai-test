"""Failure cluster read APIs (API-130/131)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.models import FailureCluster
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
VALID_CATEGORIES = frozenset(
    {
        "env_down",
        "auth_expired",
        "locator_stale",
        "assertion_real_bug",
        "flaky",
        "data_issue",
        "unknown",
    }
)
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _clustering_projection(result_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not result_summary:
        return {
            "generation_status": "ready",
            "degraded": False,
            "unclustered_refs": [],
        }
    clustering = result_summary.get("clustering")
    if not isinstance(clustering, dict):
        return {
            "generation_status": "ready",
            "degraded": False,
            "unclustered_refs": [],
        }
    generation_status = str(clustering.get("generation_status", "ready"))
    degraded = bool(clustering.get("degraded", False))
    raw_unclustered = clustering.get("unclustered_refs", [])
    unclustered: list[str] = []
    if isinstance(raw_unclustered, list):
        unclustered = [str(item) for item in raw_unclustered]
    return {
        "generation_status": generation_status,
        "degraded": degraded,
        "unclustered_refs": unclustered,
    }


def _serialize_list_item(row: FailureCluster) -> dict[str, Any]:
    confidence = float(row.confidence)
    return {
        "id": str(row.id),
        "test_run_id": str(row.test_run_id),
        "category": row.category,
        "root_cause": row.root_cause,
        "confidence": confidence,
        "blocking_judgment": row.blocking_judgment,
        "evidence_refs": [str(item) for item in row.evidence_refs],
        "failure_refs": [str(item) for item in row.failure_refs],
        "created_at": _iso(row.created_at),
    }


def _fixes_preview(row: FailureCluster) -> list[dict[str, Any]]:
    fixes = row.fixes or []
    preview: list[dict[str, Any]] = []
    for item in fixes:
        if not isinstance(item, dict):
            continue
        preview.append(
            {
                "field": str(item.get("field", "")),
                "current": str(item.get("current", "")),
                "suggested": str(item.get("suggested", "")),
                "reason": str(item.get("reason", "")),
                "confidence": float(item.get("confidence", 0.0)),
                "can_auto_apply": False,
            }
        )
    return preview


async def _require_run_session_read(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
) -> uuid.UUID:
    run = await run_query.get_run_clustering_context(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=run["project_id"],
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return run["project_id"]


async def _require_cluster_session_read(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    failure_cluster_id: uuid.UUID,
) -> tuple[FailureCluster, uuid.UUID]:
    row = await repo.get_failure_cluster(
        session,
        organization_id=ctx.organization.id,
        failure_cluster_id=failure_cluster_id,
    )
    if row is None:
        raise ValueError("not_found")
    project_id = await _require_run_session_read(session, ctx, test_run_id=row.test_run_id)
    return row, project_id


def _compute_unclustered_refs(
    *,
    failed_rows: list[Any],
    cluster_rows: list[FailureCluster],
    projection_unclustered: list[str],
    generation_status: str,
) -> list[str]:
    if generation_status == "pending":
        return list(projection_unclustered)
    if projection_unclustered:
        return projection_unclustered
    clustered_ids: set[str] = set()
    for cluster in cluster_rows:
        clustered_ids.update(str(item) for item in cluster.failure_refs)
    leftover = [str(row.id) for row in failed_rows if str(row.id) not in clustered_ids]
    return leftover


async def list_failure_clusters_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
    category: str | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    await _require_run_session_read(session, ctx, test_run_id=test_run_id)
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")
    run = await run_query.get_run_clustering_context(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
    )
    assert run is not None
    projection = _clustering_projection(run["result_summary"])
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_failure_clusters_for_run(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
        category=category,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=fetch_limit,
    )
    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]
    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = repo.encode_created_id_cursor(created_at=last.created_at, item_id=last.id)
    failed_rows = await repo.list_failed_case_results_for_run(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
    )
    unclustered_refs = _compute_unclustered_refs(
        failed_rows=failed_rows,
        cluster_rows=rows,
        projection_unclustered=projection["unclustered_refs"],
        generation_status=str(projection["generation_status"]),
    )
    return {
        "test_run_id": str(test_run_id),
        "items": [_serialize_list_item(row) for row in rows],
        "unclustered_refs": unclustered_refs,
        "generation_status": projection["generation_status"],
        "degraded": projection["degraded"],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_failure_cluster_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    failure_cluster_id: uuid.UUID,
) -> dict[str, Any]:
    row, _project_id = await _require_cluster_session_read(
        session,
        ctx,
        failure_cluster_id=failure_cluster_id,
    )
    payload = _serialize_list_item(row)
    payload["correction_history"] = list(row.correction_history or [])
    payload["fixes_preview"] = _fixes_preview(row)
    if row.unclustered_refs:
        payload["unclustered_refs"] = [str(item) for item in row.unclustered_refs]
    return payload
