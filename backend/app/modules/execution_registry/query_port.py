"""Cross-module read-only queries for execution_registry (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import repository as repo


async def get_environment_for_start(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
) -> dict[str, Any] | None:
    return await get_environment_for_run(
        session,
        organization_id=organization_id,
        environment_id=environment_id,
    )


async def get_environment_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
) -> dict[str, Any] | None:
    env = await repo.get_environment(
        session,
        organization_id=organization_id,
        environment_id=environment_id,
    )
    if env is None:
        return None
    return {
        "status": env.status,
        "version": env.aggregate_version,
        "config_version": env.config_version,
        "env_type": env.env_type,
        "scope_level": env.scope_level,
        "project_id": env.project_id,
        "name": env.name,
        "endpoint": env.endpoint,
        "credential_ref": env.credential_ref,
        "health_status": env.health_status,
        "capacity": env.capacity,
        "credential_present": bool(env.credential_ref and env.credential_ref.strip()),
    }


async def get_job_contract_for_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
    job_id: str,
) -> dict[str, Any] | None:
    contract = await repo.get_job_contract(
        session,
        organization_id=organization_id,
        execution_environment_id=environment_id,
        job_id=job_id,
    )
    if contract is None:
        return None
    return {
        "job_id": contract.job_id,
        "params_schema_ref": contract.params_schema_ref,
        "params_schema": contract.params_schema,
        "artifact_manifest": contract.artifact_manifest,
        "report_adapter": contract.report_adapter,
        "supports_cancel": contract.supports_cancel,
        "contract_version": contract.contract_version,
    }


async def list_environments_for_execution_options(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[dict[str, Any]]:
    rows = await repo.list_environments(
        session,
        organization_id=organization_id,
        project_id=project_id,
        limit=200,
    )
    items: list[dict[str, Any]] = []
    for env in rows:
        selectable = env.status == "ACTIVE"
        unavailable_reason: str | None = None
        if env.status != "ACTIVE":
            unavailable_reason = "not_active"
        elif env.status == "DEGRADED":
            unavailable_reason = "degraded"
        items.append(
            {
                "id": env.id,
                "name": env.name,
                "env_type": env.env_type,
                "status": env.status,
                "selectable": selectable,
                "unavailable_reason": unavailable_reason,
                "health_status": env.health_status,
                "capacity": env.capacity,
                "credential_present": bool(env.credential_ref and env.credential_ref.strip()),
                "version": env.aggregate_version,
            }
        )
    return items
