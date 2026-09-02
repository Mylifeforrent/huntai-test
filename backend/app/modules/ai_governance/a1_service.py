"""A1 generation orchestration — accept, background run, poll, drafts, SSE."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.errors import error_envelope
from app.modules.ai_governance import repository as repo
from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.ai_governance.models import A1Generation, AIInvocationLog
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quota_governance import query_port as quota_query
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.test_assets import query_port as test_assets_query
from app.modules.test_assets.source_parser import build_draft_case, parse_source_content

COMMAND_TYPE_GENERATION = "ai.generation.create"
READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})
VALID_SOURCE_TYPES = frozenset({"openapi", "postman", "curl"})
TERMINAL_STATUSES = frozenset({"succeeded", "partial", "failed"})
PROMPT_VERSION = "a1.v1"

RESTRICTED_MARKERS = (
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _detect_classification(content: str) -> str:
    for marker in RESTRICTED_MARKERS:
        if marker in content:
            return "Restricted"
    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("data_classification") == "Restricted":
            return "Restricted"
    except json.JSONDecodeError:
        pass
    return "Confidential"


async def _require_project_role(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    allowed: frozenset[str],
) -> None:
    if not await identity_query.project_exists_in_org(
        session, organization_id=ctx.organization.id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in allowed:
        if role is None:
            raise ValueError("not_found")
        raise ValueError("forbidden")


async def _kill_switch_blocks(session: AsyncSession, organization_id: uuid.UUID) -> bool:
    controls = await identity_query.get_capability_controls(
        session, organization_id=organization_id
    )
    if controls.get("ai_global_tightened") is True:
        return True
    tightened = [str(item) for item in controls.get("tightened_capabilities", [])]
    return "A1" in tightened


def _reject_non_json_spec(source_type: str, content: str) -> None:
    stripped = content.lstrip()
    if stripped.startswith(("---", "openapi:", "swagger:")):
        raise ValueError("file_validation")
    if source_type not in {"openapi", "postman"}:
        return
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("file_validation") from exc
    if not isinstance(data, dict):
        raise ValueError("file_validation")


@dataclass(frozen=True)
class GenerationCreateInput:
    project_id: uuid.UUID
    source_type: str
    import_source_id: uuid.UUID | None = None
    inline_content: str | None = None
    case_type_policy: dict[str, Any] | None = None


def _build_accept_response(generation_id: uuid.UUID, accepted_at: datetime) -> dict[str, Any]:
    return {
        "data": {
            "receipt": {
                "id": str(generation_id),
                "command_type": COMMAND_TYPE_GENERATION,
                "status": "accepted",
                "accepted_at": _iso(accepted_at),
                "resource_type": "generation",
                "resource_id": str(generation_id),
            },
            "generation_id": str(generation_id),
            "poll": {
                "path": f"/api/v1/ai/generations/{generation_id}",
                "sse_path": f"/api/v1/ai/generations/{generation_id}/events",
                "drafts_path": f"/api/v1/ai/generations/{generation_id}/drafts",
            },
        }
    }


async def create_generation_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: GenerationCreateInput,
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    await _require_project_role(session, ctx, project_id=body.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_TYPE_GENERATION,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {}), False

    if body.source_type not in VALID_SOURCE_TYPES:
        raise ValueError("validation")
    if body.import_source_id is None and not body.inline_content:
        raise ValueError("validation")

    content: str | None = body.inline_content
    classification = "Confidential"
    if body.import_source_id is not None:
        source = await test_assets_query.get_import_source_content(
            session,
            organization_id=ctx.organization.id,
            import_source_id=body.import_source_id,
            project_id=body.project_id,
        )
        if source is None:
            raise ValueError("not_found")
        content = str(source["content_text"])
        classification = str(source["data_classification"])
    elif content:
        classification = _detect_classification(content)
        _reject_non_json_spec(body.source_type, content)

    if classification == "Restricted":
        raise ValueError("policy")
    if await _kill_switch_blocks(session, ctx.organization.id):
        raise ValueError("policy")
    if await quota_query.token_budget_exhausted(session, organization_id=ctx.organization.id):
        raise ValueError("quota")

    now = datetime.now(UTC)
    generation_id = uuid.uuid4()
    row = A1Generation(
        id=generation_id,
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        project_id=body.project_id,
        status="accepted",
        import_source_id=body.import_source_id,
        inline_content=body.inline_content if body.import_source_id is None else None,
        drafts=None,
        failed_items=None,
        degraded=False,
        invocation_log_id=None,
        accepted_at=now,
        completed_at=None,
        error=None,
    )
    await repo.insert_a1_generation(session, row)
    response = _build_accept_response(generation_id, now)
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_TYPE_GENERATION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="ai.generation.create",
            resource_type="generation",
            resource_id=generation_id,
            project_id=body.project_id,
            result="accepted",
            request_hash=request_hash,
        ),
    )
    return response, True


async def run_generation_background(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    generation_id: uuid.UUID,
    source_type: str | None = None,
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        row = await repo.get_a1_generation(
            session,
            organization_id=organization_id,
            generation_id=generation_id,
            for_update=True,
        )
        if row is None:
            return
        now = datetime.now(UTC)
        row.status = "running"
        row.updated_at = now
        await session.commit()

        content = row.inline_content or ""
        classification = "Confidential"
        resolved_source_type = source_type
        if row.import_source_id is not None:
            source = await test_assets_query.get_import_source_content(
                session,
                organization_id=organization_id,
                import_source_id=row.import_source_id,
                project_id=row.project_id,
            )
            if source is None:
                row.status = "failed"
                row.error = error_envelope(
                    code="HT-RES-001",
                    error_class="permission",
                    subclass="not_found",
                    message="Import source not found",
                    retryable=False,
                    trace_id=str(generation_id),
                )
                row.completed_at = datetime.now(UTC)
                row.updated_at = row.completed_at
                await session.commit()
                return
            content = str(source["content_text"])
            classification = str(source["data_classification"])
            resolved_source_type = str(source["source_type"])
        if not resolved_source_type:
            row.status = "failed"
            row.error = error_envelope(
                code="HT-VAL-001",
                error_class="business",
                subclass="validation",
                message="Missing source type",
                retryable=False,
                trace_id=str(generation_id),
            )
            row.completed_at = datetime.now(UTC)
            row.updated_at = row.completed_at
            await session.commit()
            return

        invoke_output = await invoke(
            session,
            InvokeInput(
                organization_id=organization_id,
                user_id=user_id,
                task_type="general",
                prompt_version=PROMPT_VERSION,
                capability_id="A1",
                data_classification=classification,
            ),
        )
        row.invocation_log_id = invoke_output.log_id

        if invoke_output.result == "refused":
            row.status = "failed"
            refusal = invoke_output.refusal_class
            if refusal == "quota":
                error_code, error_class, subclass, retryable = (
                    "HT-QUOTA-001",
                    "business",
                    "quota",
                    True,
                )
            else:
                error_code, error_class, subclass, retryable = (
                    "HT-POL-001",
                    "permission",
                    "policy_deny",
                    False,
                )
            row.error = error_envelope(
                code=error_code,
                error_class=error_class,
                subclass=subclass,
                message="Generation refused",
                retryable=retryable,
                trace_id=str(generation_id),
            )
            row.completed_at = datetime.now(UTC)
            row.updated_at = row.completed_at
            await session.commit()
            return

        degraded = invoke_output.result == "degraded"
        row.degraded = degraded

        try:
            parse_result = parse_source_content(resolved_source_type, content)
        except ValueError:
            row.status = "failed"
            row.error = error_envelope(
                code="HT-VAL-003",
                error_class="business",
                subclass="validation",
                message="Source parse failed",
                retryable=False,
                trace_id=str(generation_id),
            )
            row.completed_at = datetime.now(UTC)
            row.updated_at = row.completed_at
            await session.commit()
            return

        failed_items = list(parse_result.failed_items)
        cases = [build_draft_case(ep) for ep in parse_result.endpoints]

        if cases and failed_items:
            row.status = "partial"
            row.drafts = cases
            row.failed_items = failed_items
        elif cases:
            row.status = "succeeded"
            row.drafts = cases
            row.failed_items = []
        else:
            row.status = "failed"
            row.drafts = []
            row.failed_items = failed_items
            row.error = error_envelope(
                code="HT-ASYNC-002",
                error_class="business",
                subclass="async_partial",
                message="No cases generated",
                retryable=False,
                trace_id=str(generation_id),
            )

        row.completed_at = datetime.now(UTC)
        row.updated_at = row.completed_at
        await session.commit()


def serialize_generation_status(row: A1Generation) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generation_id": str(row.id),
        "status": row.status,
        "project_id": str(row.project_id),
        "accepted_at": _iso(row.accepted_at),
        "completed_at": _iso(row.completed_at),
        "degraded": row.degraded,
        "drafts_available": row.status in {"succeeded", "partial"},
    }
    if row.status == "partial" and row.failed_items:
        payload["failed_items_preview"] = row.failed_items[:5]
    if row.status == "failed" and row.error:
        payload["error"] = row.error.get("error", row.error)
    return payload


async def get_generation_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    generation_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_a1_generation(
        session,
        organization_id=ctx.organization.id,
        generation_id=generation_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    return serialize_generation_status(row)


async def get_generation_drafts_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    generation_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_a1_generation(
        session,
        organization_id=ctx.organization.id,
        generation_id=generation_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)

    if row.status in {"accepted", "running"}:
        raise ValueError("state")
    if row.status == "failed":
        raise ValueError("async_failed")

    model_name = "degraded-stub"
    if row.invocation_log_id is not None:
        result = await session.execute(
            select(AIInvocationLog).where(
                AIInvocationLog.organization_id == ctx.organization.id,
                AIInvocationLog.id == row.invocation_log_id,
            )
        )
        log_row = result.scalar_one_or_none()
        if log_row is not None:
            model_name = log_row.model

    payload: dict[str, Any] = {
        "generation_id": str(row.id),
        "status": row.status,
        "cases": row.drafts or [],
        "failed_items": row.failed_items if row.failed_items is not None else [],
        "meta": {"prompt_version": PROMPT_VERSION, "model": model_name},
    }
    if row.degraded:
        payload["degraded"] = True
    return payload
