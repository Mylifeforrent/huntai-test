"""Cross-module read-only queries for approval_policy (no ORM export)."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy import repository as repo


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
