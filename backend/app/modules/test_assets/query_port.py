"""Cross-module read-only queries for test_assets (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.test_assets import repository as repo


async def get_import_source_content(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    import_source_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_import_source(
        session,
        organization_id=organization_id,
        source_id=import_source_id,
    )
    if row is None or row.project_id != project_id:
        return None
    return {
        "id": row.id,
        "source_type": row.source_type,
        "project_id": row.project_id,
        "content_text": row.content_text,
        "data_classification": row.data_classification,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "created_at": row.created_at,
    }


async def get_import_source_metadata(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    import_source_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_import_source(
        session,
        organization_id=organization_id,
        source_id=import_source_id,
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "source_type": row.source_type,
        "project_id": row.project_id,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "data_classification": row.data_classification,
        "created_at": row.created_at,
    }


async def get_cases_for_run_validation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    case_ids: list[uuid.UUID],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = await repo.get_test_case(
            session,
            organization_id=organization_id,
            test_case_id=case_id,
        )
        if case is None or case.project_id != project_id:
            continue
        version = None
        if case.current_version_id is not None:
            version = await repo.get_test_case_version(
                session,
                organization_id=organization_id,
                version_id=case.current_version_id,
            )
        snapshot = version.snapshot if version is not None else {}
        rows.append(
            {
                "id": case.id,
                "title": case.title,
                "lifecycle_status": case.lifecycle_status,
                "validity": case.validity,
                "execution_mode": case.execution_mode,
                "job_binding": case.job_binding,
                "version_id": case.current_version_id,
                "steps": snapshot.get("steps", []),
                "assertions": snapshot.get("assertions", []),
            }
        )
    return rows


async def list_cases_for_execution_options(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    execution_source: str | None = None,
) -> list[dict[str, Any]]:
    cases = await repo.list_test_cases(
        session,
        organization_id=organization_id,
        project_id=project_id,
        limit=500,
    )
    items: list[dict[str, Any]] = []
    for case in cases:
        binding = case.job_binding
        job_id: str | None = None
        if isinstance(binding, dict) and isinstance(binding.get("job_id"), str):
            job_id = binding["job_id"]
        base_selectable = (
            case.lifecycle_status == "ACTIVE"
            and case.validity == "valid"
            and (
                execution_source is None
                or (execution_source == "agent" and case.execution_mode == "agent")
                or (
                    execution_source in {"script", "external_ci"}
                    and case.execution_mode == "script"
                )
            )
        )
        selectable = base_selectable
        unavailable_reason: str | None = None
        if case.lifecycle_status != "ACTIVE":
            unavailable_reason = "not_active"
        elif case.validity != "valid":
            unavailable_reason = "invalid"
        elif execution_source == "external_ci":
            if case.case_type != "referenced":
                selectable = False
                unavailable_reason = "not_referenced"
            elif not isinstance(binding, dict) or not job_id:
                selectable = False
                unavailable_reason = "missing_job_binding"
        elif execution_source == "script" and case.case_type == "referenced":
            selectable = False
            unavailable_reason = "referenced_only_external_ci"
        elif (execution_source == "agent" and case.execution_mode != "agent") or (
            execution_source in {"script", "external_ci"} and case.execution_mode != "script"
        ):
            unavailable_reason = "mode_mismatch"
            selectable = False
        items.append(
            {
                "id": case.id,
                "title": case.title,
                "lifecycle_status": case.lifecycle_status,
                "validity": case.validity,
                "execution_mode": case.execution_mode,
                "case_type": case.case_type,
                "job_id": job_id,
                "selectable": selectable,
                "unavailable_reason": unavailable_reason,
            }
        )
    return items


async def get_test_case_pointer(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
) -> dict[str, Any] | None:
    case = await repo.get_test_case(
        session,
        organization_id=organization_id,
        test_case_id=test_case_id,
    )
    if case is None:
        return None
    return {
        "id": case.id,
        "project_id": case.project_id,
        "lifecycle_status": case.lifecycle_status,
        "aggregate_version": case.aggregate_version,
        "current_version_id": case.current_version_id,
    }
