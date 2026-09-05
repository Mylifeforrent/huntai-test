"""Cross-module read-only queries for integration_hub (dict projections only)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub import repository as repo


def _connector_ready(connector: Any) -> bool:
    has_credential = bool(connector.credential_ref and connector.credential_ref.strip())
    return connector.type == "jira" and connector.outbound_write_enabled and has_credential


async def get_ci_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> dict[str, Any] | None:
    rows = await repo.list_connectors(
        session,
        organization_id=organization_id,
        connector_type="ci",
        cursor_created_at=None,
        cursor_id=None,
        limit=None,
    )
    for row in rows:
        return {
            "id": row.id,
            "type": row.type,
            "name": row.name,
        }
    return None


async def get_jira_write_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> dict[str, Any] | None:
    rows = await repo.list_connectors(
        session,
        organization_id=organization_id,
        connector_type="jira",
        cursor_created_at=None,
        cursor_id=None,
        limit=None,
    )
    for row in rows:
        if _connector_ready(row):
            return {
                "id": row.id,
                "type": row.type,
                "name": row.name,
                "outbound_write_enabled": row.outbound_write_enabled,
                "has_credential": True,
            }
    return None


__all__ = ["get_ci_connector", "get_jira_write_connector"]
