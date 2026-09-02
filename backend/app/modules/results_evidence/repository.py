import base64
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_models import AuditEvent
from app.modules.results_evidence.models import CaseResult, StepRun


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


async def insert_case_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    test_run_id: uuid.UUID,
    test_case_id: uuid.UUID,
    test_case_version_id: uuid.UUID | None,
    attempt_seq: int,
    outcome: str,
    is_late: bool,
    is_partial: bool,
    chunk_key: str | None,
    normalized_summary: dict[str, Any] | None,
    data_classification: str,
) -> CaseResult:
    row = CaseResult(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        test_run_id=test_run_id,
        test_case_id=test_case_id,
        test_case_version_id=test_case_version_id,
        attempt_seq=attempt_seq,
        outcome=outcome,
        is_late=is_late,
        is_partial=is_partial,
        chunk_key=chunk_key,
        normalized_summary=normalized_summary,
        data_classification=data_classification,
    )
    session.add(row)
    await session.flush()
    return row


async def insert_step_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    case_result_id: uuid.UUID,
    step_index: int,
    action: dict[str, Any] | None,
    observation_ref: str | None,
    assertion_results: dict[str, Any] | None,
    token_usage: dict[str, Any] | None,
    is_incomplete: bool,
) -> StepRun:
    row = StepRun(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        case_result_id=case_result_id,
        step_index=step_index,
        action=action,
        observation_ref=observation_ref,
        assertion_results=assertion_results,
        token_usage=token_usage,
        is_incomplete=is_incomplete,
    )
    session.add(row)
    await session.flush()
    return row


async def list_case_results_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    outcome: str | None = None,
    is_late: bool | None = None,
    is_partial: bool | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[CaseResult]:
    query = (
        select(CaseResult)
        .where(
            CaseResult.organization_id == organization_id,
            CaseResult.test_run_id == test_run_id,
        )
        .order_by(CaseResult.created_at.asc(), CaseResult.id.asc())
    )
    if outcome is not None:
        query = query.where(CaseResult.outcome == outcome)
    if is_late is not None:
        query = query.where(CaseResult.is_late == is_late)
    if is_partial is not None:
        query = query.where(CaseResult.is_partial == is_partial)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                CaseResult.created_at > cursor_created_at,
                and_(
                    CaseResult.created_at == cursor_created_at,
                    CaseResult.id > cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_case_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    case_result_id: uuid.UUID,
) -> CaseResult | None:
    result = await session.execute(
        select(CaseResult).where(
            CaseResult.organization_id == organization_id,
            CaseResult.id == case_result_id,
        )
    )
    return result.scalar_one_or_none()


async def list_step_runs_for_case_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    case_result_id: uuid.UUID,
    cursor_step_index: int | None = None,
    limit: int | None = None,
) -> list[StepRun]:
    query = (
        select(StepRun)
        .where(
            StepRun.organization_id == organization_id,
            StepRun.case_result_id == case_result_id,
        )
        .order_by(StepRun.step_index.asc())
    )
    if cursor_step_index is not None:
        query = query.where(StepRun.step_index > cursor_step_index)
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
