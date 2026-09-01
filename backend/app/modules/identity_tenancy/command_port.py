"""Cross-module commands for identity_tenancy (no ORM export to consumers)."""

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.models import DEFAULT_CAPABILITY_CONTROLS

VALID_LEVELS = frozenset({"global", "ability", "module", "connector"})


def _normalize_target(target: dict[str, Any]) -> tuple[str, str | None]:
    level = str(target.get("level", ""))
    if level not in VALID_LEVELS:
        raise ValueError("validation")
    identifier: str | None = None
    if level == "ability":
        raw = target.get("capability_id") or target.get("id")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    elif level == "module":
        raw = target.get("module") or target.get("id")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    elif level == "connector":
        raw = target.get("connector_id") or target.get("id")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    return level, identifier


def _loosen_controls(
    controls: dict[str, Any], *, level: str, identifier: str | None
) -> dict[str, Any]:
    updated = deepcopy(controls)
    for key, default in DEFAULT_CAPABILITY_CONTROLS.items():
        updated.setdefault(key, deepcopy(default) if isinstance(default, list) else default)

    if level == "global":
        updated["ai_global_tightened"] = False
        updated["banner_scope"] = None
    elif level == "ability" and identifier is not None:
        caps = [str(item) for item in updated.get("tightened_capabilities", [])]
        updated["tightened_capabilities"] = [item for item in caps if item != identifier]
        if not updated["tightened_capabilities"] and not updated.get("ai_global_tightened"):
            updated["banner_scope"] = None
    elif level == "module" and identifier is not None:
        mods = [str(item) for item in updated.get("tightened_modules", [])]
        updated["tightened_modules"] = [item for item in mods if item != identifier]
        if not updated["tightened_modules"] and not updated.get("ai_global_tightened"):
            updated["banner_scope"] = None
    elif level == "connector" and identifier is not None:
        conns = [str(item) for item in updated.get("tightened_connectors", [])]
        updated["tightened_connectors"] = [item for item in conns if item != identifier]

    return updated


async def apply_kill_switch_restore(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    target: dict[str, Any],
) -> int:
    """Loosen capability_controls for an approved kill_switch_restore. Returns new version."""
    org = await repo.get_organization_by_id(session, organization_id)
    if org is None:
        raise ValueError("not_found")

    level, identifier = _normalize_target(target)
    org.capability_controls = _loosen_controls(
        org.capability_controls, level=level, identifier=identifier
    )
    org.updated_at = datetime.now(UTC)
    org.aggregate_version += 1
    await session.flush()
    return org.aggregate_version
