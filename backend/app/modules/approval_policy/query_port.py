"""Cross-module read-only queries for approval_policy (no ORM export)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy import repository as repo
from app.modules.identity_tenancy import query_port as identity_query


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


async def get_action_preview_meta(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    preview_id: uuid.UUID,
) -> tuple[str | None, datetime] | None:
    """Return (action_type, expires_at) for a preview, or None if missing."""
    record = await repo.get_action_preview_record(
        session,
        organization_id=organization_id,
        preview_id=preview_id,
    )
    if record is None:
        return None
    action_type = record.preview_payload.get("action_type")
    parsed_type = action_type if isinstance(action_type, str) else None
    return parsed_type, record.expires_at


async def _can_view_approval_for_workbench(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    caller_id: uuid.UUID,
    approval: Any,
    memberships: list[tuple[uuid.UUID, str]],
    is_owner_admin: bool,
) -> bool:
    if approval.initiator_id == caller_id:
        return True
    if approval.approver_id == caller_id or approval.escalate_to == caller_id:
        return True
    if is_owner_admin:
        return True
    roles = {role for _, role in memberships}
    if "owner" in roles or "admin" in roles:
        return True
    if "viewer" in roles or "tester" in roles:
        return await identity_query.users_share_project(
            session,
            organization_id=organization_id,
            user_id_a=caller_id,
            user_id_b=approval.initiator_id,
        )
    return False


def _serialize_workbench_approval(approval: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(approval.id),
        "action_type": approval.action_type,
        "status": approval.status,
        "expires_at": _iso(approval.expires_at),
        "initiator_id": str(approval.initiator_id),
        "target_object_type": approval.target_object_type,
        "target_object_id": str(approval.target_object_id),
        "version": approval.aggregate_version,
    }
    if approval.escalate_to is not None:
        item["escalate_to"] = str(approval.escalate_to)
    return item


async def list_workbench_pending_approvals(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    caller_id: uuid.UUID,
    project_ids: list[uuid.UUID],
    limit: int,
) -> list[dict[str, Any]]:
    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=organization_id, user_id=caller_id
    )
    is_owner_admin = await identity_query.caller_is_owner_or_admin(
        session, organization_id=organization_id, user_id=caller_id
    )
    now = datetime.now(UTC)
    rows = await repo.list_workbench_pending_approvals(
        session,
        organization_id=organization_id,
        project_ids=project_ids,
        now=now,
        limit=limit * 3,
    )
    visible: list[dict[str, Any]] = []
    for approval in rows:
        if not await _can_view_approval_for_workbench(
            session,
            organization_id=organization_id,
            caller_id=caller_id,
            approval=approval,
            memberships=memberships,
            is_owner_admin=is_owner_admin,
        ):
            continue
        visible.append(_serialize_workbench_approval(approval))
        if len(visible) >= limit:
            break
    return visible
