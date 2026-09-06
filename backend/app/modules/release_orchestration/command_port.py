"""Cross-module commands for release_orchestration (no ORM export)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.release_orchestration import service


async def prepare_release_task_after_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    approval_id: uuid.UUID,
    param_hash: str,
    actor_user_id: uuid.UUID | None,
    request_hash: str,
) -> str:
    return await service.prepare_after_approval(
        session,
        organization_id=organization_id,
        release_task_id=release_task_id,
        approval_id=approval_id,
        param_hash=param_hash,
        actor_user_id=actor_user_id,
        request_hash=request_hash,
    )


async def apply_release_observation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    body: dict[str, Any],
    request_hash: str,
) -> str:
    release_task_raw = body.get("release_task_id")
    if not isinstance(release_task_raw, str):
        return "ignored"
    try:
        release_task_id = uuid.UUID(release_task_raw)
    except ValueError:
        return "ignored"
    external_item_id = body.get("external_item_id")
    return await service.apply_release_observation(
        session,
        organization_id=organization_id,
        release_task_id=release_task_id,
        external_item_id=str(external_item_id) if external_item_id is not None else None,
        request_hash=request_hash,
    )


async def cancel_release_task_from_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
) -> str:
    """Reject/cancel path: PENDING_CONFIRM → CANCELLED (no item created)."""
    from app.modules.release_orchestration import repository as repo

    task = await repo.get_release_task(
        session,
        organization_id=organization_id,
        release_task_id=release_task_id,
        for_update=True,
    )
    if task is None or task.status != "PENDING_CONFIRM":
        return "ignored"
    from app.modules.release_orchestration import repository as repo_cas

    await repo_cas.cas_transition(
        session,
        run=task,
        new_status="CANCELLED",
        expected_status="PENDING_CONFIRM",
        updated_at=service._now(),
    )
    return "cancelled"
