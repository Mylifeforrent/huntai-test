"""Cross-module commands for test_assets (no ORM export to consumers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.test_assets import repository as repo
from app.modules.test_assets.models import TestCase, TestCaseVersion
from app.modules.test_assets.service import _build_snapshot

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


async def create_script_draft_from_trajectory(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by: uuid.UUID | None,
    title: str,
    steps: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    source_test_run_id: uuid.UUID,
) -> dict[str, Any]:
    """API-068: trajectory → new TestCase DRAFT; the source run is untouched."""
    now = datetime.now(UTC)
    case_id = uuid.uuid4()
    version_id = uuid.uuid4()
    tags = ["ai-generated"]
    snapshot = _build_snapshot(
        title=title,
        priority="P2",
        tags=tags,
        case_type="api",
        execution_mode="script",
        drafts=[{"steps": steps, "assertions": assertions}],
        script=None,
    )
    case = TestCase(
        id=case_id,
        organization_id=organization_id,
        created_at=now,
        updated_at=now,
        created_by=created_by,
        aggregate_version=1,
        project_id=project_id,
        case_type="api",
        execution_mode="script",
        title=title,
        priority="P2",
        tags=tags,
        lifecycle_status="DRAFT",
        validity="valid",
        invalid_reason=None,
        invalidated_at=None,
        script_ref=None,
        job_binding=None,
        jira_story_key=None,
        current_version_id=version_id,
    )
    version = TestCaseVersion(
        id=version_id,
        organization_id=organization_id,
        created_at=now,
        created_by=created_by,
        test_case_id=case_id,
        version_seq=1,
        snapshot=snapshot,
        data_classification="Internal",
    )
    session.add(case)
    await session.flush()
    session.add(version)
    await session.flush()
    return {
        "id": str(case_id),
        "project_id": str(project_id),
        "case_type": "api",
        "execution_mode": "script",
        "title": title,
        "priority": "P2",
        "tags": tags,
        "lifecycle_status": "DRAFT",
        "validity": "valid",
        "version": 1,
        "source_test_run_id": str(source_test_run_id),
    }
