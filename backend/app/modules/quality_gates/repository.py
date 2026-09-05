import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates.models import (
    CommandIdempotencyRecord,
    GateEvaluation,
    QualityGatePolicy,
)


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def encode_updated_id_cursor(*, updated_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": updated_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_updated_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        updated_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return updated_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:  # fmt: skip
        raise ValueError("invalid_cursor") from exc


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


async def get_policy(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    policy_id: uuid.UUID,
    for_update: bool = False,
) -> QualityGatePolicy | None:
    query = select(QualityGatePolicy).where(
        QualityGatePolicy.organization_id == organization_id,
        QualityGatePolicy.id == policy_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_policies(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    mode: str | None = None,
    cursor_updated_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int,
) -> list[QualityGatePolicy]:
    query = (
        select(QualityGatePolicy)
        .where(
            QualityGatePolicy.organization_id == organization_id,
            QualityGatePolicy.project_id == project_id,
        )
        .order_by(QualityGatePolicy.updated_at.desc(), QualityGatePolicy.id.desc())
    )
    if mode is not None:
        query = query.where(QualityGatePolicy.mode == mode)
    if cursor_updated_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                QualityGatePolicy.updated_at < cursor_updated_at,
                and_(
                    QualityGatePolicy.updated_at == cursor_updated_at,
                    QualityGatePolicy.id < cursor_id,
                ),
            )
        )
    query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def insert_policy(session: AsyncSession, row: QualityGatePolicy) -> QualityGatePolicy:
    session.add(row)
    await session.flush()
    return row


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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:  # fmt: skip
        raise ValueError("invalid_cursor") from exc


async def insert_gate_evaluation(session: AsyncSession, row: GateEvaluation) -> GateEvaluation:
    session.add(row)
    await session.flush()
    return row


async def delete_gate_evaluation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> None:
    row = await get_gate_evaluation(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
        for_update=True,
    )
    if row is None:
        return
    await session.delete(row)
    await session.flush()


async def get_gate_evaluation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    for_update: bool = False,
) -> GateEvaluation | None:
    query = select(GateEvaluation).where(
        GateEvaluation.organization_id == organization_id,
        GateEvaluation.id == evaluation_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_gate_evaluation_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> GateEvaluation | None:
    result = await session.execute(
        select(GateEvaluation)
        .where(
            GateEvaluation.organization_id == organization_id,
            GateEvaluation.test_run_id == test_run_id,
        )
        .order_by(GateEvaluation.created_at.desc(), GateEvaluation.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_gate_evaluations(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_ids: list[uuid.UUID] | None,
    test_run_id: uuid.UUID | None,
    result_filter: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int,
) -> list[GateEvaluation]:
    if test_run_ids is not None and len(test_run_ids) == 0:
        return []
    query = select(GateEvaluation).where(GateEvaluation.organization_id == organization_id)
    if test_run_ids is not None:
        query = query.where(GateEvaluation.test_run_id.in_(test_run_ids))
    if test_run_id is not None:
        query = query.where(GateEvaluation.test_run_id == test_run_id)
    if result_filter == "waived":
        query = query.where(GateEvaluation.waiver_approval_id.is_not(None))
    elif result_filter is not None:
        query = query.where(
            GateEvaluation.result == result_filter,
            GateEvaluation.waiver_approval_id.is_(None),
        )
    if created_from is not None:
        query = query.where(GateEvaluation.created_at >= created_from)
    if created_to is not None:
        query = query.where(GateEvaluation.created_at <= created_to)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                GateEvaluation.created_at < cursor_created_at,
                and_(
                    GateEvaluation.created_at == cursor_created_at,
                    GateEvaluation.id < cursor_id,
                ),
            )
        )
    query = query.order_by(GateEvaluation.created_at.desc(), GateEvaluation.id.desc())
    query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def cas_attach_waiver(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
    waiver_approval_id: uuid.UUID,
) -> bool:
    row = await get_gate_evaluation(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
        for_update=True,
    )
    if row is None or row.waiver_approval_id is not None:
        return False
    row.waiver_approval_id = waiver_approval_id
    await session.flush()
    return True


async def get_policy_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> QualityGatePolicy | None:
    result = await session.execute(
        select(QualityGatePolicy)
        .where(
            QualityGatePolicy.organization_id == organization_id,
            QualityGatePolicy.project_id == project_id,
        )
        .order_by(QualityGatePolicy.updated_at.desc(), QualityGatePolicy.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
