import base64
import json
import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_models import AuditEvent


def encode_created_id_cursor(*, created_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_created_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return created_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


async def list_audit_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    request_hash: str | None = None,
    approval_id: uuid.UUID | None = None,
    approval_bound_hash: str | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    external_request_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[AuditEvent]:
    query = (
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    )
    if actor_user_id is not None:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    if request_hash is not None:
        query = query.where(AuditEvent.request_hash == request_hash)
    if approval_id is not None:
        query = query.where(AuditEvent.approval_id == approval_id)
    if approval_bound_hash is not None:
        query = query.where(AuditEvent.approval_bound_hash == approval_bound_hash)
    if resource_type is not None:
        query = query.where(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        query = query.where(AuditEvent.resource_id == resource_id)
    if project_id is not None:
        query = query.where(AuditEvent.project_id == project_id)
    if external_request_id is not None:
        query = query.where(AuditEvent.external_request_id == external_request_id)
    if created_from is not None:
        query = query.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        query = query.where(AuditEvent.created_at <= created_to)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                AuditEvent.created_at < cursor_created_at,
                and_(
                    AuditEvent.created_at == cursor_created_at,
                    AuditEvent.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_audit_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    audit_event_id: uuid.UUID,
) -> AuditEvent | None:
    result = await session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.id == audit_event_id,
        )
    )
    return result.scalar_one_or_none()
