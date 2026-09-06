"""Repository for release_orchestration (no cross-module ORM export)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.release_orchestration.models import (
    Base,  # noqa: F401 — re-export for alembic autogen parity
    CommandIdempotencyRecord,
    ReleaseItemRef,
    ReleaseTask,
)

TERMINAL_STATUSES = frozenset({"READY", "CANCELLED"})
VALID_STATUSES = frozenset(
    {"DRAFT", "PENDING_CONFIRM", "SUBMITTED", "READY", "FAILED_RETRYABLE", "CANCELLED"}
)


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


async def get_release_task(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    for_update: bool = False,
) -> ReleaseTask | None:
    query = select(ReleaseTask).where(
        ReleaseTask.organization_id == organization_id,
        ReleaseTask.id == release_task_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_release_tasks(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    status: str | None = None,
) -> list[ReleaseTask]:
    query = select(ReleaseTask).where(
        ReleaseTask.organization_id == organization_id,
        ReleaseTask.project_id == project_id,
    )
    if status is not None:
        query = query.where(ReleaseTask.status == status)
    query = query.order_by(ReleaseTask.created_at.desc(), ReleaseTask.id.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def insert_release_task(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    project_id: uuid.UUID,
    jira_version_ref: str,
    scope_snapshot: dict[str, Any],
    task_id: uuid.UUID | None = None,
) -> ReleaseTask:
    row = ReleaseTask(
        id=task_id or uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        project_id=project_id,
        jira_version_ref=jira_version_ref,
        status="DRAFT",
        scope_snapshot=scope_snapshot,
    )
    session.add(row)
    await session.flush()
    return row


async def get_item_ref_by_prepare_key(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    prepare_key: str,
) -> ReleaseItemRef | None:
    result = await session.execute(
        select(ReleaseItemRef).where(
            ReleaseItemRef.organization_id == organization_id,
            ReleaseItemRef.prepare_key == prepare_key,
        )
    )
    return result.scalar_one_or_none()


async def insert_item_ref(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    external_system: str,
    external_item_id: str,
    prepare_key: str,
    created_at: datetime,
) -> ReleaseItemRef:
    row = ReleaseItemRef(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        release_task_id=release_task_id,
        external_system=external_system,
        external_item_id=external_item_id,
        prepare_key=prepare_key,
    )
    session.add(row)
    await session.flush()
    return row


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
    response_ref: dict[str, Any] | None,
    created_by: uuid.UUID | None,
    created_at: datetime,
) -> None:
    session.add(
        CommandIdempotencyRecord(
            id=uuid.uuid4(),
            organization_id=organization_id,
            command_type=command_type,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref=response_ref,
            created_by=created_by,
            created_at=created_at,
        )
    )
    await session.flush()


async def cas_transition(
    session: AsyncSession,
    *,
    run: ReleaseTask,
    new_status: str,
    expected_status: str,
    updated_at: datetime,
) -> bool:
    if run.status != expected_status:
        return False
    run.status = new_status
    run.updated_at = updated_at
    run.aggregate_version += 1
    await session.flush()
    return True
