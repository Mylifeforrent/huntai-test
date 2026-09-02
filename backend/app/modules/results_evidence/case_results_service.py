"""CaseResult / StepRun read APIs (API-064–066)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionOrToken
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.models import CaseResult
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
VALID_OUTCOMES = frozenset({"passed", "failed", "incomplete"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_case_result_list_item(row: CaseResult) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": _iso(row.created_at),
        "test_run_id": str(row.test_run_id),
        "test_case_id": str(row.test_case_id),
        "test_case_version_id": str(row.test_case_version_id) if row.test_case_version_id else None,
        "attempt_seq": row.attempt_seq,
        "outcome": row.outcome,
        "is_late": row.is_late,
        "is_partial": row.is_partial,
        "chunk_key": row.chunk_key,
        "data_classification": row.data_classification,
    }


async def _require_run_read(
    session: AsyncSession,
    auth: SessionOrToken,
    *,
    test_run_id: uuid.UUID,
) -> uuid.UUID:
    org_id = auth.organization_id
    run = await run_query.get_run_scope(
        session,
        organization_id=org_id,
        test_run_id=test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    if auth.token is not None:
        allowed = list(auth.token.project_ids)
        if run["project_id"] not in allowed:
            raise ValueError("not_found")
        return run["project_id"]
    assert auth.session is not None
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=run["project_id"],
        user_id=auth.session.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return run["project_id"]


async def list_case_results_for_caller(
    session: AsyncSession,
    auth: SessionOrToken,
    *,
    test_run_id: uuid.UUID,
    outcome: str | None,
    is_late: bool | None,
    is_partial: bool | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    await _require_run_read(session, auth, test_run_id=test_run_id)
    if outcome is not None and outcome not in VALID_OUTCOMES:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_case_results_for_run(
        session,
        organization_id=auth.organization_id,
        test_run_id=test_run_id,
        outcome=outcome,
        is_late=is_late,
        is_partial=is_partial,
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
    return {
        "items": [serialize_case_result_list_item(row) for row in rows],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_case_result_for_caller(
    session: AsyncSession,
    auth: SessionOrToken,
    *,
    case_result_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_case_result(
        session,
        organization_id=auth.organization_id,
        case_result_id=case_result_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_run_read(session, auth, test_run_id=row.test_run_id)
    payload = serialize_case_result_list_item(row)
    payload["normalized_summary"] = row.normalized_summary
    payload["artifact_ids"] = []
    return payload


async def list_step_runs_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    case_result_id: uuid.UUID,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    row = await repo.get_case_result(
        session,
        organization_id=ctx.organization.id,
        case_result_id=case_result_id,
    )
    if row is None:
        raise ValueError("not_found")
    run = await run_query.get_run_scope(
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
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    cursor_step: int | None = None
    if cursor is not None:
        try:
            cursor_step = int(cursor)
        except ValueError as exc:
            raise ValueError("invalid_cursor") from exc
    if limit is not None and limit < 1:
        raise ValueError("validation")
    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_step_runs_for_case_result(
        session,
        organization_id=ctx.organization.id,
        case_result_id=case_result_id,
        cursor_step_index=cursor_step,
        limit=fetch_limit,
    )
    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]
    next_cursor: str | None = None
    if has_more and rows:
        next_cursor = str(rows[-1].step_index)
    items = [
        {
            "id": str(item.id),
            "created_at": _iso(item.created_at),
            "case_result_id": str(item.case_result_id),
            "step_index": item.step_index,
            "action": item.action,
            "observation_ref": item.observation_ref,
            "assertion_results": item.assertion_results,
            "token_usage": item.token_usage,
            "is_incomplete": item.is_incomplete,
        }
        for item in rows
    ]
    return {"items": items, "page": {"next_cursor": next_cursor, "has_more": has_more}}
