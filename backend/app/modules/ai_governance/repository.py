import base64
import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.models import AIInvocationLog, CommandIdempotencyRecord, ModelRoute


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


async def get_model_route(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    model_route_id: uuid.UUID,
) -> ModelRoute | None:
    result = await session.execute(
        select(ModelRoute).where(
            ModelRoute.organization_id == organization_id,
            ModelRoute.id == model_route_id,
        )
    )
    return result.scalar_one_or_none()


async def get_model_route_by_task(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    task_type: str,
    data_classification: str,
) -> ModelRoute | None:
    result = await session.execute(
        select(ModelRoute).where(
            ModelRoute.organization_id == organization_id,
            ModelRoute.task_type == task_type,
            ModelRoute.data_classification == data_classification,
        )
    )
    return result.scalar_one_or_none()


async def list_model_routes(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    task_type: str | None,
    data_classification: str | None,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int | None,
) -> list[ModelRoute]:
    query = (
        select(ModelRoute)
        .where(ModelRoute.organization_id == organization_id)
        .order_by(ModelRoute.created_at.desc(), ModelRoute.id.desc())
    )
    if task_type is not None:
        query = query.where(ModelRoute.task_type == task_type)
    if data_classification is not None:
        query = query.where(ModelRoute.data_classification == data_classification)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                ModelRoute.created_at < cursor_created_at,
                and_(
                    ModelRoute.created_at == cursor_created_at,
                    ModelRoute.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_model_route(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    task_type: str,
    data_classification: str,
    provider_allowlist: list[str],
    max_cost: Decimal,
    fallback: dict[str, Any] | None,
    require_prompt_version: bool,
    require_structured_output: bool,
    credential_ref: str | None,
) -> ModelRoute:
    route = ModelRoute(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        task_type=task_type,
        data_classification=data_classification,
        provider_allowlist=provider_allowlist,
        max_cost=max_cost,
        fallback=fallback,
        require_prompt_version=require_prompt_version,
        require_structured_output=require_structured_output,
        credential_ref=credential_ref,
    )
    session.add(route)
    await session.flush()
    return route


async def insert_invocation_log(
    session: AsyncSession,
    *,
    log_id: uuid.UUID,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    user_id: uuid.UUID | None,
    model: str,
    prompt_version: str,
    usage: dict[str, Any],
    cost: Decimal,
    latency_ms: int,
    data_classification: str,
    result: str,
    skill_version_id: uuid.UUID | None = None,
    model_route_id: uuid.UUID | None = None,
    copilot_session_id: uuid.UUID | None = None,
    input_ref: str | None = None,
) -> AIInvocationLog:
    row = AIInvocationLog(
        id=log_id,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        user_id=user_id,
        model=model,
        prompt_version=prompt_version,
        usage=usage,
        cost=cost,
        latency_ms=latency_ms,
        data_classification=data_classification,
        result=result,
        skill_version_id=skill_version_id,
        model_route_id=model_route_id,
        copilot_session_id=copilot_session_id,
        input_ref=input_ref,
    )
    session.add(row)
    await session.flush()
    return row


async def get_invocation_log(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    log_id: uuid.UUID,
) -> AIInvocationLog | None:
    result = await session.execute(
        select(AIInvocationLog).where(
            AIInvocationLog.organization_id == organization_id,
            AIInvocationLog.id == log_id,
        )
    )
    return result.scalar_one_or_none()


async def list_invocation_logs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    result_filter: str | None,
    model: str | None,
    copilot_session_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int | None,
) -> list[AIInvocationLog]:
    query = (
        select(AIInvocationLog)
        .where(AIInvocationLog.organization_id == organization_id)
        .order_by(AIInvocationLog.created_at.desc(), AIInvocationLog.id.desc())
    )
    if user_id is not None:
        query = query.where(AIInvocationLog.user_id == user_id)
    if result_filter is not None:
        query = query.where(AIInvocationLog.result == result_filter)
    if model is not None:
        query = query.where(AIInvocationLog.model == model)
    if copilot_session_id is not None:
        query = query.where(AIInvocationLog.copilot_session_id == copilot_session_id)
    if created_from is not None:
        query = query.where(AIInvocationLog.created_at >= created_from)
    if created_to is not None:
        query = query.where(AIInvocationLog.created_at <= created_to)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                AIInvocationLog.created_at < cursor_created_at,
                and_(
                    AIInvocationLog.created_at == cursor_created_at,
                    AIInvocationLog.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_invocation_logs_in_window(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_from: datetime,
    created_to: datetime,
) -> list[AIInvocationLog]:
    result = await session.execute(
        select(AIInvocationLog).where(
            AIInvocationLog.organization_id == organization_id,
            AIInvocationLog.created_at >= created_from,
            AIInvocationLog.created_at <= created_to,
        )
    )
    return list(result.scalars().all())
