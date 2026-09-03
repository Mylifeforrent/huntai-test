"""Cross-module read-only queries for quality_gates (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.evaluation_service import serialize_detail
from app.modules.quality_gates.service import serialize_detail as serialize_policy_detail
from app.modules.run_orchestration import query_port as run_query


async def get_policy_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_policy_for_project(
        session,
        organization_id=organization_id,
        project_id=project_id,
    )
    if row is None:
        return None
    return serialize_policy_detail(row)


async def get_evaluation_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    evaluation_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_gate_evaluation(
        session,
        organization_id=organization_id,
        evaluation_id=evaluation_id,
    )
    if row is None:
        return None
    run = await run_query.get_run_for_gate(
        session,
        organization_id=organization_id,
        test_run_id=row.test_run_id,
    )
    payload = serialize_detail(row)
    if run is not None:
        payload["project_id"] = str(run["project_id"])
    return payload


async def get_evaluation_for_test_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_gate_evaluation_for_run(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    if row is None:
        return None
    run = await run_query.get_run_for_gate(
        session,
        organization_id=organization_id,
        test_run_id=test_run_id,
    )
    payload = serialize_detail(row)
    if run is not None:
        payload["project_id"] = str(run["project_id"])
    return payload
