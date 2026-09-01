import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import (
    ActionPreviewRecord,
    ApprovalRequest,
    CommandIdempotencyRecord,
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
    project_id: uuid.UUID | None = None,
    expected_target_version: int | None = None,
    origin_request_id: uuid.UUID | None = None,
    original_initiator_id: uuid.UUID | None = None,
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
        origin_request_id=origin_request_id,
        original_initiator_id=original_initiator_id,
        snapshot_ref=None,
        side_effect_level=side_effect_level,
        project_id=project_id,
        expected_target_version=expected_target_version,
    )
    session.add(approval)
    await session.flush()
    return approval


async def create_action_preview_record(
    session: AsyncSession,
    *,
    preview_id: uuid.UUID,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    expires_at: datetime,
    preview_payload: dict[str, Any],
) -> ActionPreviewRecord:
    record = ActionPreviewRecord(
        id=preview_id,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        expires_at=expires_at,
        preview_payload=preview_payload,
    )
    session.add(record)
    await session.flush()
    return record


async def get_action_preview_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    preview_id: uuid.UUID,
) -> ActionPreviewRecord | None:
    result = await session.execute(
        select(ActionPreviewRecord).where(
            ActionPreviewRecord.organization_id == organization_id,
            ActionPreviewRecord.id == preview_id,
        )
    )
    return result.scalar_one_or_none()


async def get_approval_request(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    approval_request_id: uuid.UUID,
    for_update: bool = False,
) -> ApprovalRequest | None:
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.organization_id == organization_id,
        ApprovalRequest.id == approval_request_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_approval_requests(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    status: str | None = None,
    action_type: str | None = None,
    target_object_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    visibility_filter: Any | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    fetch_limit: int | None = None,
    now: datetime | None = None,
) -> list[ApprovalRequest]:
    conditions = [ApprovalRequest.organization_id == organization_id]
    if status is not None:
        if status == "EXPIRED" and now is not None:
            conditions.append(
                or_(
                    ApprovalRequest.status == "EXPIRED",
                    and_(
                        ApprovalRequest.status == "PENDING",
                        ApprovalRequest.expires_at < now,
                    ),
                )
            )
        else:
            conditions.append(ApprovalRequest.status == status)
    if action_type is not None:
        conditions.append(ApprovalRequest.action_type == action_type)
    if target_object_id is not None:
        conditions.append(ApprovalRequest.target_object_id == target_object_id)
    if project_id is not None:
        conditions.append(ApprovalRequest.project_id == project_id)
    if visibility_filter is not None:
        conditions.append(visibility_filter)
    if cursor_created_at is not None and cursor_id is not None:
        conditions.append(
            or_(
                ApprovalRequest.created_at < cursor_created_at,
                and_(
                    ApprovalRequest.created_at == cursor_created_at,
                    ApprovalRequest.id < cursor_id,
                ),
            )
        )

    stmt = (
        select(ApprovalRequest)
        .where(*conditions)
        .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
    )
    if fetch_limit is not None:
        stmt = stmt.limit(fetch_limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_workbench_pending_approvals(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    now: datetime,
    limit: int,
) -> list[ApprovalRequest]:
    if not project_ids:
        return []
    project_condition = or_(
        ApprovalRequest.project_id.in_(project_ids),
        ApprovalRequest.project_id.is_(None),
    )
    conditions = [
        ApprovalRequest.organization_id == organization_id,
        ApprovalRequest.status.in_(("CREATED", "PENDING")),
        project_condition,
        or_(
            ApprovalRequest.status == "CREATED",
            and_(
                ApprovalRequest.status == "PENDING",
                ApprovalRequest.expires_at >= now,
            ),
        ),
    ]
    stmt = (
        select(ApprovalRequest)
        .where(*conditions)
        .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
