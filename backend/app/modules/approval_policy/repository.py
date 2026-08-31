import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest, CommandIdempotencyRecord


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


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


async def create_approval_request(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    action_type: str,
    target_object_type: str,
    target_object_id: uuid.UUID,
    action_payload: dict[str, Any],
    param_hash: str,
    card_payload: dict[str, Any],
    side_effect_level: str,
    initiator_id: uuid.UUID,
    approver_id: uuid.UUID,
    expires_at: datetime,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        action_type=action_type,
        target_object_type=target_object_type,
        target_object_id=target_object_id,
        action_payload=action_payload,
        param_hash=param_hash,
        card_payload=card_payload,
        status="PENDING",
        execution_result=None,
        initiator_id=initiator_id,
        approver_id=approver_id,
        expires_at=expires_at,
        escalate_to=None,
        expired_reason=None,
        origin_request_id=None,
        original_initiator_id=None,
        snapshot_ref=None,
        side_effect_level=side_effect_level,
    )
    session.add(approval)
    await session.flush()
    return approval


async def count_approval_requests(session: AsyncSession) -> int:
    result = await session.execute(select(ApprovalRequest.id))
    return len(list(result.scalars().all()))
