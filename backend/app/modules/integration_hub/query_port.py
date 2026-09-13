"""Cross-module read-only queries for integration_hub (dict projections only)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import loopback_issuer_host
from app.modules.integration_hub import repository as repo


def _connector_ready(connector: Any) -> bool:
    has_credential = bool(connector.credential_ref and connector.credential_ref.strip())
    return connector.type == "jira" and connector.outbound_write_enabled and has_credential


def _loopback_base_url(connector: Any) -> str | None:
    contract = connector.action_contract if isinstance(connector.action_contract, dict) else {}
    base_url = contract.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    stripped = base_url.strip().rstrip("/")
    if loopback_issuer_host(stripped) is None:
        return None
    return stripped


async def get_connector_pointer_by_type(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_type: str,
) -> dict[str, Any] | None:
    rows = await repo.list_connectors(
        session,
        organization_id=organization_id,
        connector_type=connector_type,
        cursor_created_at=None,
        cursor_id=None,
        limit=50,
    )
    for row in rows:
        return {"id": row.id, "type": row.type, "name": row.name}
    return None


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


async def get_loopback_outbound_target(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_type: str,
) -> dict[str, Any] | None:
    """Return a loopback mock outbound target, or None to keep in-process stubs.

    Non-loopback ``base_url`` values are ignored (fail-close: never HTTP to a
    real vendor from this local-mock path). Connectors without ``base_url`` are
    skipped so existing tests that seed connectors without a mock URL stay stub.
    """
    if connector_type not in repo.VALID_CONNECTOR_TYPES:
        return None
    rows = await repo.list_connectors(
        session,
        organization_id=organization_id,
        connector_type=connector_type,
        cursor_created_at=None,
        cursor_id=None,
        limit=None,
    )
    for row in rows:
        if not row.outbound_write_enabled:
            continue
        base_url = _loopback_base_url(row)
        if base_url is None:
            continue
        contract = row.action_contract if isinstance(row.action_contract, dict) else {}
        return {
            "id": row.id,
            "type": row.type,
            "name": row.name,
            "base_url": base_url,
            "credential_ref": row.credential_ref,
            "action_contract": dict(contract),
        }
    return None


__all__ = [
    "get_ci_connector",
    "get_jira_write_connector",
    "get_loopback_outbound_target",
    "get_connector_pointer_by_type",
]
