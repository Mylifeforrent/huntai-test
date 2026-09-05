"""EvidenceObject search and evidence-package export (API-026/027/028, API-223).

Export is async: API-028 only accepts the command (CommandReceipt). The
authoritative completion is the package Artifact registered for the receipt and
readable through API-223 — receipt status and SSE progress never prove
completion by themselves (AC-096).
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import object_store
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.results_evidence.models import EvidenceObject
from app.modules.run_orchestration import command_port as run_command
from app.modules.run_orchestration import query_port as run_query

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
EXPORT_ROLES = frozenset({"owner", "admin", "tester"})
EXPORT_FORMATS = frozenset({"zip", "md", "json"})
EXPORT_COMMAND_TYPE = "evidence_export"
EXPORT_RESOURCE_TYPE = "ExportPackage"
EXPORT_ARTIFACT_KIND = "export_package"
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
_CLASSIFICATION_RANK = {"Public": 0, "Internal": 1, "Confidential": 2}

_MIME_BY_FORMAT = {
    "zip": "application/zip",
    "md": "text/markdown",
    "json": "application/json",
}


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_evidence_object(row: EvidenceObject) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": _iso(row.created_at),
        "created_by": str(row.created_by) if row.created_by else None,
        "claim": row.claim,
        "source_object": dict(row.source_object or {}),
        "content_ref": row.content_ref,
        "subject_type": row.subject_type,
        "subject_id": str(row.subject_id),
        "data_classification": row.data_classification,
    }


async def _resolve_subject_test_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
) -> uuid.UUID | None:
    if subject_type == "test_run":
        scope = await run_query.get_run_scope(
            session,
            organization_id=organization_id,
            test_run_id=subject_id,
        )
        return scope["id"] if scope is not None else None
    if subject_type == "case_result":
        case_result = await repo.get_case_result(
            session,
            organization_id=organization_id,
            case_result_id=subject_id,
        )
        return case_result.test_run_id if case_result is not None else None
    if subject_type == "failure_cluster":
        cluster = await repo.get_failure_cluster(
            session,
            organization_id=organization_id,
            failure_cluster_id=subject_id,
        )
        return cluster.test_run_id if cluster is not None else None
    return None


async def _require_evidence_read(
    session: AsyncSession,
    ctx: SessionContext,
    row: EvidenceObject,
) -> uuid.UUID | None:
    """Authorize one evidence row; returns its project_id (None = org-level)."""
    organization_id = ctx.organization.id
    run_id = await _resolve_subject_test_run(
        session,
        organization_id=organization_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
    )
    if run_id is None:
        # Unresolvable subject: org-level evidence, owner/admin only (fail-close).
        if not await identity_query.caller_is_owner_or_admin(
            session, organization_id=organization_id, user_id=ctx.user.id
        ):
            raise ValueError("not_found")
        return None
    scope = await run_query.get_run_scope(
        session,
        organization_id=organization_id,
        test_run_id=run_id,
    )
    if scope is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=organization_id,
        project_id=scope["project_id"],
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return scope["project_id"]


def _clamp_limit(limit: int | None) -> int:
    if limit is None or limit <= 0:
        return DEFAULT_PAGE_LIMIT
    return min(limit, MAX_PAGE_LIMIT)


async def list_evidence_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    if (subject_type is None) != (subject_id is None):
        raise ValueError("validation")
    cursor_created_at: datetime | None = None
    cursor_item_id: uuid.UUID | None = None
    if cursor is not None:
        try:
            cursor_created_at, cursor_item_id = repo.decode_created_id_cursor(cursor)
        except ValueError as exc:
            raise ValueError("invalid_cursor") from exc
    page_limit = _clamp_limit(limit)
    rows = await repo.list_evidence_objects(
        session,
        organization_id=ctx.organization.id,
        subject_type=subject_type,
        subject_id=subject_id,
        created_from=created_from,
        created_to=created_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_item_id,
        limit=page_limit,
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            await _require_evidence_read(session, ctx, row)
        except ValueError:
            continue
        items.append(serialize_evidence_object(row))
    # Cursor advances over the raw page (opaque id); unauthorized rows are
    # dropped from items only, so pagination stays stable across pages.
    has_more = len(rows) > page_limit
    next_cursor = None
    if has_more and rows:
        last = rows[page_limit - 1]
        next_cursor = repo.encode_created_id_cursor(created_at=last.created_at, item_id=last.id)
    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    return {"items": items, "page": page}


async def get_evidence_object_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    evidence_object_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_evidence_object(
        session,
        organization_id=ctx.organization.id,
        evidence_object_id=evidence_object_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_evidence_read(session, ctx, row)
    return serialize_evidence_object(row)


def _receipt_payload(
    *,
    receipt_id: uuid.UUID,
    status: str,
    accepted_at: datetime,
) -> dict[str, Any]:
    return {
        "id": str(receipt_id),
        "command_type": EXPORT_COMMAND_TYPE,
        "status": status,
        "accepted_at": _iso(accepted_at),
        "resource_type": EXPORT_RESOURCE_TYPE,
        "resource_id": str(receipt_id),
        "poll": {
            "path": f"/api/v1/command-receipts/{receipt_id}",
            "sse_path": f"/api/v1/command-receipts/{receipt_id}/events",
        },
    }


def _validate_export_scope(
    *,
    evidence_object_ids: list[uuid.UUID] | None,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
    export_format: str,
) -> None:
    if export_format not in EXPORT_FORMATS:
        raise ValueError("validation")
    if evidence_object_ids is not None and subject_id is not None:
        raise ValueError("validation")
    if evidence_object_ids is not None and not evidence_object_ids:
        raise ValueError("validation")
    if (subject_type is None) != (subject_id is None):
        raise ValueError("validation")
    if evidence_object_ids is None and subject_id is None:
        raise ValueError("validation")


async def _load_export_rows(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    evidence_object_ids: list[uuid.UUID] | None,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
) -> list[EvidenceObject]:
    if evidence_object_ids is not None:
        rows = await repo.list_evidence_objects_by_ids(
            session,
            organization_id=ctx.organization.id,
            evidence_ids=evidence_object_ids,
        )
        found = {row.id for row in rows}
        if any(item not in found for item in evidence_object_ids):
            raise ValueError("not_found")
        return rows
    assert subject_type is not None and subject_id is not None
    rows = await repo.list_evidence_objects(
        session,
        organization_id=ctx.organization.id,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    if not rows:
        raise ValueError("not_found")
    return rows


def _evidence_markdown(row: EvidenceObject) -> str:
    source = dict(row.source_object or {})
    lines = [
        f"## Evidence {row.id}",
        "",
        f"- claim: {row.claim}",
        f"- subject: {row.subject_type} {row.subject_id}",
        f"- data_classification: {row.data_classification}",
        f"- created_at: {_iso(row.created_at)}",
        (
            "- source_object: " + json.dumps(source, ensure_ascii=False, sort_keys=True)
            if source
            else "- source_object: {}"
        ),
        f"- content_ref: {row.content_ref if row.content_ref else '(none)'}",
        "",
    ]
    return "\n".join(lines)


def _build_package_bytes(
    *,
    export_format: str,
    rows: list[EvidenceObject],
    receipt_id: uuid.UUID,
    generated_at: datetime,
) -> bytes:
    payload = {
        "receipt_id": str(receipt_id),
        "generated_at": _iso(generated_at),
        "format": export_format,
        "evidence": [serialize_evidence_object(row) for row in rows],
    }
    if export_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if export_format == "md":
        header = f"# Evidence package {receipt_id}\n\ngenerated_at: {_iso(generated_at)}\n\n"
        return (header + "\n".join(_evidence_markdown(row) for row in rows)).encode("utf-8")
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "receipt_id": str(receipt_id),
            "generated_at": _iso(generated_at),
            "format": export_format,
            "evidence_count": len(rows),
            "evidence_ids": [str(row.id) for row in rows],
        }
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        for index, row in enumerate(rows, start=1):
            name = f"evidence/{index:04d}_{row.subject_type}_{str(row.id)[:8]}.md"
            archive.writestr(name, _evidence_markdown(row))
    return buffer.getvalue()


def _max_classification(rows: list[EvidenceObject]) -> str:
    rank = -1
    result = "Internal"
    for row in rows:
        candidate = _CLASSIFICATION_RANK.get(row.data_classification)
        if candidate is not None and candidate > rank:
            rank = candidate
            result = row.data_classification
    return result


async def _export_project_scope(
    session: AsyncSession,
    ctx: SessionContext,
    rows: list[EvidenceObject],
    *,
    expected_project_id: uuid.UUID | None,
) -> uuid.UUID:
    """Resolve the single owning project of the selection; fail-close otherwise."""
    project_ids: set[uuid.UUID] = set()
    for row in rows:
        project_id = await _require_evidence_read(session, ctx, row)
        if project_id is None:
            raise ValueError("forbidden")
        project_ids.add(project_id)
    if len(project_ids) != 1:
        raise ValueError("validation")
    project_id = next(iter(project_ids))
    if expected_project_id is not None and project_id != expected_project_id:
        raise ValueError("validation")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in EXPORT_ROLES:
        raise ValueError("forbidden")
    return project_id


async def create_export_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    export_format: str,
    evidence_object_ids: list[uuid.UUID] | None,
    subject_type: str | None,
    subject_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], list[uuid.UUID]]:
    _validate_export_scope(
        evidence_object_ids=evidence_object_ids,
        subject_type=subject_type,
        subject_id=subject_id,
        export_format=export_format,
    )
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=EXPORT_COMMAND_TYPE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {}), []

    rows = await _load_export_rows(
        session,
        ctx,
        evidence_object_ids=evidence_object_ids,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    # Restricted evidence never leaves the platform (AC-096); the whole request
    # is denied instead of silently filtered.
    if any(row.data_classification == "Restricted" for row in rows):
        raise ValueError("policy_deny")
    resolved_project_id = await _export_project_scope(
        session, ctx, rows, expected_project_id=project_id
    )

    now = datetime.now(UTC)
    receipt_id = uuid.uuid4()
    payload = _receipt_payload(receipt_id=receipt_id, status="accepted", accepted_at=now)
    await run_command.create_command_receipt_for_command(
        session,
        receipt_id=receipt_id,
        organization_id=ctx.organization.id,
        created_at=now,
        created_by=ctx.user.id,
        command_type=EXPORT_COMMAND_TYPE,
        status="accepted",
        resource_type=EXPORT_RESOURCE_TYPE,
        resource_id=receipt_id,
        project_id=resolved_project_id,
    )
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=EXPORT_COMMAND_TYPE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="evidence.export.accepted",
            resource_type=EXPORT_RESOURCE_TYPE,
            resource_id=receipt_id,
            project_id=resolved_project_id,
            result="accepted",
            request_hash=request_hash,
            evidence_refs=[row.id for row in rows],
        ),
    )
    return payload, [row.id for row in rows]


async def run_export_packaging(
    *,
    organization_id: uuid.UUID,
    receipt_id: uuid.UUID,
    evidence_ids: list[uuid.UUID],
    export_format: str,
    created_by: uuid.UUID | None,
) -> None:
    """Background packaging after acceptance; receipt is the only progress owner."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            rows = await repo.list_evidence_objects_by_ids(
                session,
                organization_id=organization_id,
                evidence_ids=evidence_ids,
            )
            if len(rows) != len(evidence_ids):
                raise ValueError("not_found")
            if any(row.data_classification == "Restricted" for row in rows):
                raise ValueError("policy_deny")
            await run_command.update_command_receipt_status(
                session,
                organization_id=organization_id,
                receipt_id=receipt_id,
                status="running",
            )
            await session.commit()

            now = datetime.now(UTC)
            artifact_id = uuid.uuid4()
            data = _build_package_bytes(
                export_format=export_format,
                rows=sorted(rows, key=lambda row: (row.created_at, row.id)),
                receipt_id=receipt_id,
                generated_at=now,
            )
            filename = f"evidence-package-{receipt_id}.{export_format}"
            object_key = object_store.generate_object_key(
                organization_id=organization_id,
                artifact_id=artifact_id,
                filename=filename,
            )
            checksum = object_store.write_bytes(object_key=object_key, data=data)
            await repo.insert_artifact(
                session,
                organization_id=organization_id,
                created_at=now,
                created_by=created_by,
                case_result_id=None,
                test_run_id=None,
                kind=EXPORT_ARTIFACT_KIND,
                object_key=object_key,
                checksum=checksum,
                byte_size=len(data),
                mime_type=_MIME_BY_FORMAT[export_format],
                data_classification=_max_classification(rows),
                original_filename=filename,
                artifact_id=artifact_id,
                source_receipt_id=receipt_id,
            )
            await run_command.update_command_receipt_status(
                session,
                organization_id=organization_id,
                receipt_id=receipt_id,
                status="succeeded",
            )
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=organization_id,
                    actor_user_id=created_by,
                    action="evidence.export.completed",
                    resource_type=EXPORT_RESOURCE_TYPE,
                    resource_id=receipt_id,
                    result="ok",
                    evidence_refs=evidence_ids,
                ),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            async with factory() as fail_session:
                await run_command.update_command_receipt_status(
                    fail_session,
                    organization_id=organization_id,
                    receipt_id=receipt_id,
                    status="failed",
                )
                await append_audit_event(
                    fail_session,
                    AuditAppendInput(
                        organization_id=organization_id,
                        actor_user_id=created_by,
                        action="evidence.export.failed",
                        resource_type=EXPORT_RESOURCE_TYPE,
                        resource_id=receipt_id,
                        result="failed",
                    ),
                )
                await fail_session.commit()
            raise


async def read_export_content_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    receipt_id: uuid.UUID,
) -> tuple[bytes, str, str]:
    organization_id = ctx.organization.id
    pointer = await run_query.get_command_receipt_pointer(
        session,
        organization_id=organization_id,
        receipt_id=receipt_id,
    )
    if pointer is None or pointer["command_type"] != EXPORT_COMMAND_TYPE:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=organization_id,
        project_id=pointer["project_id"],
        user_id=ctx.user.id,
    )
    # Re-verify authorization on every download; receipt_id is not a token.
    if role is None or role not in EXPORT_ROLES:
        raise ValueError("not_found")
    if pointer["status"] != "succeeded":
        raise ValueError("not_ready")
    artifact = await repo.get_artifact_by_source_receipt(
        session,
        organization_id=organization_id,
        source_receipt_id=receipt_id,
        kind=EXPORT_ARTIFACT_KIND,
    )
    if artifact is None:
        raise ValueError("not_ready")
    if artifact.data_classification == "Restricted":
        raise ValueError("policy_deny")
    if not object_store.file_exists(artifact.object_key):
        raise ValueError("not_ready")
    if not object_store.verify_checksum(artifact.object_key, artifact.checksum):
        raise ValueError("checksum_mismatch")
    data = object_store.read_bytes(artifact.object_key)
    mime = artifact.mime_type or "application/octet-stream"
    filename = object_store.sanitize_filename(
        artifact.original_filename or f"evidence-package-{receipt_id}"
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=ctx.user.id,
            action="export_package.download",
            resource_type=EXPORT_RESOURCE_TYPE,
            resource_id=receipt_id,
            project_id=pointer["project_id"],
            result="ok",
        ),
    )
    return data, mime, filename
