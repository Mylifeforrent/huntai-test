import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

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
