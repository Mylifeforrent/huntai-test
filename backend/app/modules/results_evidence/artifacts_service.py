"""Artifact metadata and proxy download (API-220 / API-221)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import object_store
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.models import Artifact
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _scan_status(row: Artifact) -> str:
    if object_store.file_exists(row.object_key) and object_store.verify_checksum(
        row.object_key, row.checksum
    ):
        return "passed"
    return "pending"


def serialize_artifact_metadata(row: Artifact) -> dict[str, Any]:
    artifact_id = str(row.id)
    return {
        "id": artifact_id,
        "created_at": _iso(row.created_at),
        "created_by": str(row.created_by) if row.created_by else None,
        "kind": row.kind,
        "object_key": row.object_key,
        "checksum": row.checksum,
        "byte_size": row.byte_size,
        "mime_type": row.mime_type,
        "data_classification": row.data_classification,
        "original_filename": row.original_filename,
        "test_run_id": str(row.test_run_id),
        "case_result_id": str(row.case_result_id) if row.case_result_id else None,
        "scan_status": _scan_status(row),
        "content_access": {
            "mode": "app_proxy",
            "content_path": f"/api/v1/artifacts/{artifact_id}/content",
        },
    }


async def _require_artifact_read(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    artifact: Artifact,
) -> uuid.UUID:
    run = await run_query.get_run_scope(
        session,
        organization_id=ctx.organization.id,
        test_run_id=artifact.test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=run["project_id"],
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return run["project_id"]


async def get_artifact_metadata_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    artifact_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_artifact(
        session,
        organization_id=ctx.organization.id,
        artifact_id=artifact_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_artifact_read(session, ctx, artifact=row)
    return serialize_artifact_metadata(row)


async def read_artifact_content_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    artifact_id: uuid.UUID,
) -> tuple[bytes, str, str]:
    row = await repo.get_artifact(
        session,
        organization_id=ctx.organization.id,
        artifact_id=artifact_id,
    )
    if row is None:
        raise ValueError("not_found")
    project_id = await _require_artifact_read(session, ctx, artifact=row)
    if row.data_classification == "Restricted":
        raise ValueError("policy_deny")
    if not object_store.file_exists(row.object_key):
        raise ValueError("not_ready")
    if not object_store.verify_checksum(row.object_key, row.checksum):
        raise ValueError("checksum_mismatch")
    data = object_store.read_bytes(row.object_key)
    mime = row.mime_type or "application/octet-stream"
    filename = object_store.sanitize_filename(row.original_filename or f"{row.kind}.bin")
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="artifact.download",
            resource_type="artifact",
            resource_id=row.id,
            project_id=project_id,
            result="ok",
        ),
    )
    return data, mime, filename
