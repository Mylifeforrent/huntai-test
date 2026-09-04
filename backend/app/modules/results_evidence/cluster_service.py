"""Failure cluster read APIs (API-130/131)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import query_port as evidence_query
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.models import FailureCluster
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})
COMMAND_CORRECT = "failure_cluster.correct"
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
VALID_BLOCKING = frozenset({"blocker", "non_blocker", "uncertain"})
CORRECTABLE_FIELDS = frozenset({"category", "blocking_judgment", "root_cause"})


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


def _serialize_list_item(
    row: FailureCluster,
    *,
    jira_issue: dict[str, str] | None = None,
) -> dict[str, Any]:
    confidence = float(row.confidence)
    payload: dict[str, Any] = {
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
    if jira_issue is not None:
        payload["jira_issue"] = jira_issue
    return payload


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
        "items": [
            _serialize_list_item(
                row,
                jira_issue=await evidence_query.get_latest_jira_issue_for_subject(
                    session,
                    organization_id=ctx.organization.id,
                    subject_type="failure_cluster",
                    subject_id=row.id,
                ),
            )
            for row in rows
        ],
        "unclustered_refs": unclustered_refs,
        "generation_status": projection["generation_status"],
        "degraded": projection["degraded"],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def _require_cluster_session_write(
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
    run = await run_query.get_run_clustering_context(
        session,
        organization_id=ctx.organization.id,
        test_run_id=row.test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=run["project_id"],
        user_id=ctx.user.id,
    )
    if role is None:
        raise ValueError("not_found")
    if role not in WRITE_ROLES:
        raise ValueError("forbidden")
    return row, run["project_id"]


def _serialize_cluster_detail(
    row: FailureCluster,
    *,
    jira_issue: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = _serialize_list_item(row, jira_issue=jira_issue)
    payload["correction_history"] = list(row.correction_history or [])
    payload["fixes_preview"] = _fixes_preview(row)
    if row.unclustered_refs:
        payload["unclustered_refs"] = [str(item) for item in row.unclustered_refs]
    return payload


def _field_value(row: FailureCluster, field: str) -> str | None:
    if field == "category":
        return row.category
    if field == "blocking_judgment":
        return row.blocking_judgment
    if field == "root_cause":
        return row.root_cause
    raise ValueError("validation")


def _apply_correction_value(
    row: FailureCluster,
    *,
    field: str,
    new_value: str | None,
) -> None:
    if field == "category":
        if new_value not in VALID_CATEGORIES:
            raise ValueError("validation")
        row.category = new_value
        return
    if field == "blocking_judgment":
        if new_value not in VALID_BLOCKING:
            raise ValueError("validation")
        row.blocking_judgment = new_value
        return
    if field == "root_cause":
        row.root_cause = new_value
        return
    raise ValueError("validation")


async def correct_failure_cluster_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    failure_cluster_id: uuid.UUID,
    corrections: list[dict[str, Any]],
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row, project_id = await _require_cluster_session_write(
        session,
        ctx,
        failure_cluster_id=failure_cluster_id,
    )
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CORRECT,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if not corrections:
        raise ValueError("validation")

    now = datetime.now(UTC)
    pending: list[tuple[str, str | None, str | None]] = []
    current_values: dict[str, str | None] = {
        "category": row.category,
        "blocking_judgment": row.blocking_judgment,
        "root_cause": row.root_cause,
    }
    for item in corrections:
        field = str(item.get("field", ""))
        if field not in CORRECTABLE_FIELDS:
            raise ValueError("validation")
        current = current_values[field]
        if "old" in item:
            old_raw = item.get("old")
            if field == "root_cause":
                old_compare = None if old_raw is None else str(old_raw)
                if old_compare != current:
                    raise ValueError("validation")
            elif str(old_raw) != current:
                raise ValueError("validation")
        new_raw = item.get("new")
        if field == "root_cause":
            new_value = None if new_raw is None else str(new_raw)
        else:
            if new_raw is None:
                raise ValueError("validation")
            new_value = str(new_raw)
        if field == "category" and new_value not in VALID_CATEGORIES:
            raise ValueError("validation")
        if field == "blocking_judgment" and new_value not in VALID_BLOCKING:
            raise ValueError("validation")
        pending.append((field, current, new_value))
        current_values[field] = new_value

    history = list(row.correction_history or [])
    for field, old_before, new_value in pending:
        _apply_correction_value(row, field=field, new_value=new_value)
        history.append(
            {
                "actor": str(ctx.user.id),
                "field": field,
                "old": old_before,
                "new": new_value,
                "timestamp": _iso(now),
            }
        )

    await repo.update_failure_cluster_corrections(
        session,
        row=row,
        category=row.category,
        root_cause=row.root_cause,
        blocking_judgment=row.blocking_judgment,
        correction_history=history,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="failure_cluster.correct",
            resource_type="failure_cluster",
            resource_id=row.id,
            project_id=project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    response = {"data": _serialize_cluster_detail(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CORRECT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


def _similarity_score(
    *,
    source_blocking: str,
    candidate_blocking: str,
) -> float:
    return 1.0 if source_blocking == candidate_blocking else 0.7


async def list_similar_failure_clusters_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    failure_cluster_id: uuid.UUID,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    row, _project_id = await _require_cluster_session_read(
        session,
        ctx,
        failure_cluster_id=failure_cluster_id,
    )
    run = await run_query.get_run_clustering_context(
        session,
        organization_id=ctx.organization.id,
        test_run_id=row.test_run_id,
    )
    assert run is not None
    if limit is not None and limit < 1:
        raise ValueError("validation")
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
    fetch_limit = None if limit is None else limit + 1
    run_ids = await run_query.list_run_ids_for_project(
        session,
        organization_id=ctx.organization.id,
        project_id=run["project_id"],
    )
    rows = await repo.list_similar_failure_clusters(
        session,
        organization_id=ctx.organization.id,
        source_cluster_id=failure_cluster_id,
        category=row.category,
        test_run_ids=run_ids,
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
    items = [
        {
            "id": str(item.id),
            "test_run_id": str(item.test_run_id),
            "category": item.category,
            "confidence": float(item.confidence),
            "similarity_score": _similarity_score(
                source_blocking=row.blocking_judgment,
                candidate_blocking=item.blocking_judgment,
            ),
            "created_at": _iso(item.created_at),
        }
        for item in rows
    ]
    return {"items": items, "page": {"next_cursor": next_cursor, "has_more": has_more}}


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
    jira_issue = await evidence_query.get_latest_jira_issue_for_subject(
        session,
        organization_id=ctx.organization.id,
        subject_type="failure_cluster",
        subject_id=row.id,
    )
    return _serialize_cluster_detail(row, jira_issue=jira_issue)
