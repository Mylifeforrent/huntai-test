import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.audit_models import AuditEvent

ALLOWED_SORT_VALUES = frozenset({None, "created_at", "-created_at"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_audit_event(row: AuditEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "created_at": _iso(row.created_at),
        "data_classification": row.data_classification,
    }
    optional_fields: list[tuple[str, Any]] = [
        ("project_id", str(row.project_id) if row.project_id is not None else None),
        ("actor_user_id", str(row.actor_user_id) if row.actor_user_id is not None else None),
        ("delegated_agent", row.delegated_agent),
        ("workflow", row.workflow),
        ("step", row.step),
        ("skill_id", str(row.skill_id) if row.skill_id is not None else None),
        (
            "skill_version_id",
            str(row.skill_version_id) if row.skill_version_id is not None else None,
        ),
        ("model", row.model),
        ("provider", row.provider),
        ("prompt_version", row.prompt_version),
        ("tool", row.tool),
        ("action", row.action),
        ("resource_type", row.resource_type),
        ("resource_id", str(row.resource_id) if row.resource_id is not None else None),
        ("request_hash", row.request_hash),
        ("response_hash", row.response_hash),
        ("approval_id", str(row.approval_id) if row.approval_id is not None else None),
        ("approval_decision", row.approval_decision),
        ("approval_bound_hash", row.approval_bound_hash),
        ("external_request_id", row.external_request_id),
        ("result", row.result),
        (
            "evidence_refs",
            [str(item) for item in row.evidence_refs] if row.evidence_refs is not None else None,
        ),
        ("cost", float(row.cost) if row.cost is not None else None),
        ("latency_ms", row.latency_ms),
        ("payload_ref", row.payload_ref),
    ]
    for key, value in optional_fields:
        payload[key] = value
    return payload


async def _require_owner_admin(session: AsyncSession, ctx: SessionContext) -> None:
    allowed = await identity_query.caller_is_owner_or_admin(
        session, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if not allowed:
        raise ValueError("forbidden")


def _paginate[T](
    rows: list[T],
    *,
    limit: int | None,
    get_created_at: Callable[[T], datetime],
    get_id: Callable[[T], uuid.UUID],
) -> tuple[list[T], dict[str, Any]]:
    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = repo.encode_created_id_cursor(
            created_at=get_created_at(last), item_id=get_id(last)
        )
    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    if limit is not None:
        page["limit"] = limit
    return rows, page


def _validate_sort(sort: str | None) -> None:
    if sort not in ALLOWED_SORT_VALUES:
        raise ValueError("validation")


async def list_audit_events_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    sort: str | None,
    actor_user_id: uuid.UUID | None,
    request_hash: str | None,
    approval_id: uuid.UUID | None,
    approval_bound_hash: str | None,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    external_request_id: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    _validate_sort(sort)
    if limit is not None and limit < 1:
        raise ValueError("validation")

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        try:
            cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
        except ValueError as exc:
            raise ValueError("invalid_cursor") from exc

    rows = await repo.list_audit_events(
        session,
        organization_id=ctx.organization.id,
        actor_user_id=actor_user_id,
        request_hash=request_hash,
        approval_id=approval_id,
        approval_bound_hash=approval_bound_hash,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
        external_request_id=external_request_id,
        created_from=created_from,
        created_to=created_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=limit,
    )
    visible, page = _paginate(
        rows,
        limit=limit,
        get_created_at=lambda item: item.created_at,
        get_id=lambda item: item.id,
    )
    return {
        "items": [serialize_audit_event(item) for item in visible],
        "page": page,
    }


async def get_audit_event_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    audit_event_id: uuid.UUID,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    row = await repo.get_audit_event(
        session,
        organization_id=ctx.organization.id,
        audit_event_id=audit_event_id,
    )
    if row is None:
        raise ValueError("not_found")
    return serialize_audit_event(row)
