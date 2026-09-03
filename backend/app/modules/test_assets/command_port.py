"""Cross-module commands for test_assets (no ORM export to consumers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.test_assets import repository as repo
from app.modules.test_assets.models import TestCaseVersion

HEAL_PATCH_WHITELIST = frozenset(
    {"assertions", "steps", "locator_health", "title", "priority", "tags"}
)


async def invalidate_case_for_missing_job(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    job_id: str,
) -> None:
    """Mark TestCase validity invalid when Jenkins job no longer exists (reversible)."""
    _ = actor_user_id
    case = await repo.get_test_case(
        session,
        organization_id=organization_id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if case is None:
        raise ValueError("not_found")
    now = datetime.now(UTC)
    case.validity = "invalid"
    case.invalid_reason = f"jenkins_job_not_found:{job_id}"
    case.invalidated_at = now
    case.updated_at = now
    case.aggregate_version += 1
    await session.flush()


async def apply_heal_after_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
    expected_target_version: int,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID,
) -> uuid.UUID:
    """Create new TestCaseVersion and switch current_version_id after heal_apply approval."""
    case = await repo.get_test_case(
        session,
        organization_id=organization_id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if case is None:
        raise ValueError("not_found")
    if case.lifecycle_status != "ACTIVE":
        raise ValueError("state")
    if case.aggregate_version != expected_target_version:
        raise ValueError("version")
    if case.current_version_id is None:
        raise ValueError("state")
    current_version = await repo.get_test_case_version(
        session,
        organization_id=organization_id,
        version_id=case.current_version_id,
    )
    if current_version is None:
        raise ValueError("state")

    new_snapshot = dict(current_version.snapshot)
    for key, value in patch.items():
        if key in HEAL_PATCH_WHITELIST:
            new_snapshot[key] = value

    now = datetime.now(UTC)
    new_version_id = uuid.uuid4()
    version_row = TestCaseVersion(
        id=new_version_id,
        organization_id=organization_id,
        created_at=now,
        created_by=actor_user_id,
        test_case_id=test_case_id,
        version_seq=current_version.version_seq + 1,
        snapshot=new_snapshot,
        data_classification=current_version.data_classification,
    )
    await repo.insert_test_case_version(session, version_row)
    case.current_version_id = new_version_id
    case.updated_at = now
    case.aggregate_version += 1
    await session.flush()
    return current_version.id
