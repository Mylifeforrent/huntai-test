import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence.audit_models import AuditEvent
from app.modules.results_evidence.models import (
    CaseResult,
    CommandIdempotencyRecord,
    EvidenceObject,
    FailureCluster,
    StepRun,
)


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


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


async def list_failed_case_results_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> list[CaseResult]:
    result = await session.execute(
        select(CaseResult)
        .where(
            CaseResult.organization_id == organization_id,
            CaseResult.test_run_id == test_run_id,
            CaseResult.outcome == "failed",
        )
        .order_by(CaseResult.created_at.asc(), CaseResult.id.asc())
    )
    return list(result.scalars().all())


async def list_step_runs_for_case_results(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    case_result_ids: list[uuid.UUID],
) -> list[StepRun]:
    if not case_result_ids:
        return []
    result = await session.execute(
        select(StepRun)
        .where(
            StepRun.organization_id == organization_id,
            StepRun.case_result_id.in_(case_result_ids),
        )
        .order_by(StepRun.case_result_id.asc(), StepRun.step_index.asc())
    )
    return list(result.scalars().all())


async def count_failure_clusters_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> int:
    result = await session.execute(
        select(FailureCluster.id).where(
            FailureCluster.organization_id == organization_id,
            FailureCluster.test_run_id == test_run_id,
        )
    )
    return len(list(result.scalars().all()))


async def insert_failure_cluster(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    test_run_id: uuid.UUID,
    category: str,
    root_cause: str | None,
    confidence: float,
    blocking_judgment: str,
    evidence_refs: list[uuid.UUID],
    failure_refs: list[uuid.UUID],
    unclustered_refs: list[uuid.UUID] | None,
    fixes: list[dict[str, Any]] | None,
) -> FailureCluster:
    row = FailureCluster(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        test_run_id=test_run_id,
        category=category,
        root_cause=root_cause,
        confidence=confidence,
        blocking_judgment=blocking_judgment,
        evidence_refs=evidence_refs,
        failure_refs=failure_refs,
        correction_history=[],
        unclustered_refs=unclustered_refs,
        fixes=fixes,
    )
    session.add(row)
    await session.flush()
    return row


async def list_failure_clusters_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    category: str | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[FailureCluster]:
    query = (
        select(FailureCluster)
        .where(
            FailureCluster.organization_id == organization_id,
            FailureCluster.test_run_id == test_run_id,
        )
        .order_by(FailureCluster.created_at.asc(), FailureCluster.id.asc())
    )
    if category is not None:
        query = query.where(FailureCluster.category == category)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                FailureCluster.created_at > cursor_created_at,
                and_(
                    FailureCluster.created_at == cursor_created_at,
                    FailureCluster.id > cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_failure_cluster(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    failure_cluster_id: uuid.UUID,
) -> FailureCluster | None:
    result = await session.execute(
        select(FailureCluster).where(
            FailureCluster.organization_id == organization_id,
            FailureCluster.id == failure_cluster_id,
        )
    )
    return result.scalar_one_or_none()


async def get_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
) -> CommandIdempotencyRecord | None:
    result = await session.execute(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.organization_id == organization_id,
            CommandIdempotencyRecord.command_type == command_type,
            CommandIdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def create_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
    request_hash: str,
    response_ref: dict[str, Any],
    created_by: uuid.UUID | None,
    created_at: datetime,
) -> CommandIdempotencyRecord:
    record = CommandIdempotencyRecord(
        id=uuid.uuid4(),
        organization_id=organization_id,
        command_type=command_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response_ref,
        created_at=created_at,
        created_by=created_by,
    )
    session.add(record)
    await session.flush()
    return record


async def insert_evidence_object(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    claim: str,
    source_object: dict[str, Any],
    content_ref: str | None,
    subject_type: str,
    subject_id: uuid.UUID,
    data_classification: str,
) -> EvidenceObject:
    row = EvidenceObject(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        claim=claim,
        source_object=source_object,
        content_ref=content_ref,
        subject_type=subject_type,
        subject_id=subject_id,
        data_classification=data_classification,
    )
    session.add(row)
    await session.flush()
    return row


async def list_evidence_objects_for_subjects(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject_type: str,
    subject_ids: list[uuid.UUID],
) -> list[EvidenceObject]:
    if not subject_ids:
        return []
    result = await session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == organization_id,
            EvidenceObject.subject_type == subject_type,
            EvidenceObject.subject_id.in_(subject_ids),
        )
    )
    return list(result.scalars().all())


async def update_failure_cluster_corrections(
    session: AsyncSession,
    *,
    row: FailureCluster,
    category: str,
    root_cause: str | None,
    blocking_judgment: str,
    correction_history: list[dict[str, Any]],
) -> FailureCluster:
    row.category = category
    row.root_cause = root_cause
    row.blocking_judgment = blocking_judgment
    row.correction_history = correction_history
    await session.flush()
    return row


async def list_similar_failure_clusters(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    source_cluster_id: uuid.UUID,
    category: str,
    test_run_ids: list[uuid.UUID],
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[FailureCluster]:
    if not test_run_ids:
        return []
    query = (
        select(FailureCluster)
        .where(
            FailureCluster.organization_id == organization_id,
            FailureCluster.id != source_cluster_id,
            FailureCluster.category == category,
            FailureCluster.test_run_id.in_(test_run_ids),
        )
        .order_by(FailureCluster.created_at.desc(), FailureCluster.id.desc())
    )
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                FailureCluster.created_at < cursor_created_at,
                and_(
                    FailureCluster.created_at == cursor_created_at,
                    FailureCluster.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
