import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_models import AuditEvent


@dataclass(frozen=True)
class AuditAppendInput:
    organization_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    result: str | None = None
    request_hash: str | None = None


@dataclass(frozen=True)
class AuditEventSummary:
    id: uuid.UUID
    created_at: datetime
    action: str | None
    resource_type: str | None
    resource_id: uuid.UUID | None


async def append_audit_event(session: AsyncSession, event: AuditAppendInput) -> uuid.UUID:
    event_id = uuid.uuid4()
    row = AuditEvent(
        id=event_id,
        organization_id=event.organization_id,
        created_at=datetime.now(UTC),
        project_id=event.project_id,
        actor_user_id=event.actor_user_id,
        delegated_agent=None,
        workflow=None,
        step=None,
        skill_id=None,
        skill_version_id=None,
        model=None,
        provider=None,
        prompt_version=None,
        tool=None,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        request_hash=event.request_hash,
        response_hash=None,
        approval_id=None,
        approval_decision=None,
        approval_bound_hash=None,
        data_classification="Internal",
        external_request_id=None,
        result=event.result,
        evidence_refs=None,
        cost=None,
        latency_ms=None,
        payload_ref=None,
    )
    session.add(row)
    return event_id


async def list_recent_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    limit: int = 50,
) -> list[AuditEventSummary]:
    """Newest ``limit`` events for the project (implementation cap, not product default)."""
    result = await session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.project_id == project_id,
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        AuditEventSummary(
            id=row.id,
            created_at=row.created_at,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
        )
        for row in rows
    ]
