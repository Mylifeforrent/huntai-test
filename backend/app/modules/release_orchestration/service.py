"""ReleaseTask services (API-150…155, FR-15, S-M3-03).

State machine (problem_model §2.6):
DRAFT → PENDING_CONFIRM → SUBMITTED → READY / FAILED_RETRYABLE → (retry|cancel).

A5 notes draft is read-only and never auto-pushed (AC-066). The only path into
the Release system is the release_push approval's internal prepare command
(AC-067); READY arrives via HMAC webhook observation (API-090), never from the
prepare call itself.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.integration_hub.query_port import get_loopback_outbound_target
from app.modules.quality_gates import query_port as gate_query
from app.modules.release_orchestration import repository as repo
from app.modules.release_orchestration.models import ReleaseTask
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration import command_port as run_command

VALID_RETRY_SOURCES = frozenset({"FAILED_RETRYABLE"})
VALID_CANCEL_SOURCES = frozenset({"PENDING_CONFIRM", "FAILED_RETRYABLE"})


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_task(row: ReleaseTask, *, include_detail: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "status": row.status,
        "jira_version_ref": row.jira_version_ref,
        "version": row.aggregate_version,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "scope_snapshot": dict(row.scope_snapshot or {}),
    }
    if include_detail:
        payload["notes_draft"] = row.notes_draft
        payload["a5"] = dict(row.a5) if row.a5 else None
        payload["gate_result_ref"] = str(row.gate_result_ref) if row.gate_result_ref else None
        payload["divergence"] = dict(row.divergence) if row.divergence else None
        payload["release_item"] = payload["scope_snapshot"].get("release_item")
    return payload


async def _require_project(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    roles: frozenset[str],
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
    if role is None:
        raise ValueError("not_found")
    if role not in roles:
        raise ValueError("forbidden")


READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})


async def list_release_tasks_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    status: str | None,
) -> dict[str, Any]:
    if status is not None and status not in repo.VALID_STATUSES:
        raise ValueError("validation")
    await _require_project(session, ctx, project_id=project_id, roles=READ_ROLES)
    rows = await repo.list_release_tasks(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        status=status,
    )
    return {"items": [serialize_task(row) for row in rows], "page": {"has_more": False}}


async def get_release_task_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    release_task_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_release_task(
        session,
        organization_id=ctx.organization.id,
        release_task_id=release_task_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project(session, ctx, project_id=row.project_id, roles=READ_ROLES)
    payload = serialize_task(row, include_detail=True)
    payload["readiness"] = await build_readiness_projection(session, ctx, task=row)
    return payload


async def build_readiness_projection(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    task: ReleaseTask,
) -> dict[str, Any]:
    latest_gate = await gate_query.get_latest_gate_evaluation_pointer(
        session,
        organization_id=ctx.organization.id,
        project_id=task.project_id,
    )
    scope = dict(task.scope_snapshot or {})
    jira_scope_ok = bool(scope.get("jira_scope_issues"))
    items = [
        {
            "key": "jira_scope",
            "level": "green" if jira_scope_ok else "red",
            "evidence_refs": [],
            "unmet": not jira_scope_ok,
        },
        {
            "key": "gate_evaluation",
            "level": (
                "green" if latest_gate is not None and latest_gate["result"] == "pass" else "red"
            ),
            "evidence_refs": [latest_gate["id"]] if latest_gate else [],
            "unmet": latest_gate is None or latest_gate["result"] != "pass",
        },
        {
            "key": "notes_draft",
            "level": "green" if task.a5 is not None else "red",
            "evidence_refs": [],
            "unmet": task.a5 is None,
        },
    ]
    overall = "red" if any(item["unmet"] for item in items) else "green"
    return {
        "release_task_id": str(task.id),
        "overall": overall,
        "items": items,
        "gate_evaluation_id": str(latest_gate["id"]) if latest_gate else None,
        "unevaluated_reason": None,
        "task_version": task.aggregate_version,
    }


async def create_release_task_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    jira_version_ref: str,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project(session, ctx, project_id=project_id, roles=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.create",
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    # Jira scope read via the org's jira connector; the M3 connector cannot read
    # scopes yet — the read is recorded as failed and the draft still lands
    # (HT-EXT-001 is only raised when no connector exists at all).
    from app.modules.integration_hub import query_port as integration_query

    connector = await integration_query.get_connector_pointer_by_type(
        session, organization_id=ctx.organization.id, connector_type="jira"
    )
    if connector is None:
        raise ValueError("ext_read")
    scope_read = "stub_unavailable"

    now = _now()
    scope_snapshot = {
        "jira_version_ref": jira_version_ref,
        "jira_scope_issues": [],
        "plan_ids": [],
        "scope_read": scope_read,
    }
    row = await repo.insert_release_task(
        session,
        organization_id=ctx.organization.id,
        created_at=now,
        created_by=ctx.user.id,
        project_id=project_id,
        jira_version_ref=jira_version_ref,
        scope_snapshot=scope_snapshot,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="release_task.create",
            resource_type="release_task",
            resource_id=row.id,
            project_id=project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    payload = serialize_task(row)
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.create",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    return payload


def _build_a5_draft(task: ReleaseTask) -> dict[str, Any]:
    scope = dict(task.scope_snapshot or {})
    issues_raw = scope.get("jira_scope_issues")
    issues: list[Any] = issues_raw if isinstance(issues_raw, list) else []
    changes = [
        {
            "jira_key": str(issue.get("jira_key", "")),
            "type": str(issue.get("type", "fix")),
            "summary": str(issue.get("summary", "")),
        }
        for issue in issues
        if isinstance(issue, dict)
    ]
    checklist = [
        {"item": "readiness_gate", "status": "missing", "evidence_ref": ""},
        {"item": "notes_review", "status": "missing", "evidence_ref": ""},
    ]
    missing_inputs: list[str] = []
    if not changes:
        missing_inputs.append("jira_scope_issues")
    missing_inputs.append("evidence_refs")
    return {
        "summary": f"Release notes draft for {task.jira_version_ref}",
        "changes": changes,
        "checklist": checklist,
        "missing_inputs": missing_inputs,
        "meta": {"generated_by": "A5_draft_builder", "degraded": True},
    }


async def advance_draft_to_pending_confirm(
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Background DRAFT → PENDING_CONFIRM: readiness evaluated + A5 draft built."""
    factory = get_session_factory()
    async with factory() as session:
        task = await repo.get_release_task(
            session,
            organization_id=organization_id,
            release_task_id=release_task_id,
            for_update=True,
        )
        if task is None or task.status != "DRAFT":
            await session.commit()
            return
        a5 = _build_a5_draft(task)
        try:
            output = await invoke(
                session,
                InvokeInput(
                    organization_id=organization_id,
                    user_id=actor_user_id or organization_id,
                    task_type="general",
                    prompt_version="release-notes@1.0.0",
                    capability_id="A5",
                    module="release_orchestration",
                    data_classification="Confidential",
                ),
            )
            a5["meta"]["ai_invocation_log_id"] = str(output.log_id)
            a5["meta"]["degraded"] = output.result != "ok"
        except ValueError:
            a5["meta"]["degraded"] = True
        notes_draft = a5["summary"]
        task.a5 = a5
        task.notes_draft = notes_draft
        await repo.cas_transition(
            session,
            run=task,
            new_status="PENDING_CONFIRM",
            expected_status="DRAFT",
            updated_at=_now(),
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="release_task.advance",
                resource_type="release_task",
                resource_id=task.id,
                project_id=task.project_id,
                result="ok",
            ),
        )
        await session.commit()


async def retry_release_task_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    release_task_id: uuid.UUID,
    expected_version: int,
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    _ = reason
    task = await repo.get_release_task(
        session,
        organization_id=ctx.organization.id,
        release_task_id=release_task_id,
        for_update=True,
    )
    if task is None:
        raise ValueError("not_found")
    await _require_project(session, ctx, project_id=task.project_id, roles=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.retry_prepare",
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})
    if task.aggregate_version != expected_version:
        raise ValueError("version")
    if task.status not in VALID_RETRY_SOURCES:
        raise ValueError("state")

    receipt_id = uuid.uuid4()
    now = _now()
    await run_command.create_command_receipt_for_command(
        session,
        receipt_id=receipt_id,
        organization_id=ctx.organization.id,
        created_at=now,
        created_by=ctx.user.id,
        command_type="release_task.retry_prepare",
        status="accepted",
        resource_type="ReleaseTask",
        resource_id=release_task_id,
        project_id=task.project_id,
    )
    await repo.cas_transition(
        session,
        run=task,
        new_status="SUBMITTED",
        expected_status="FAILED_RETRYABLE",
        updated_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="release_task.retry",
            resource_type="release_task",
            resource_id=task.id,
            project_id=task.project_id,
            result="accepted",
            request_hash=request_hash,
        ),
    )
    payload = {
        "receipt": {
            "id": str(receipt_id),
            "command_type": "release_task.retry_prepare",
            "status": "accepted",
            "accepted_at": _iso(now),
            "resource_type": "ReleaseTask",
            "resource_id": str(release_task_id),
            "poll": {"path": f"/api/v1/command-receipts/{receipt_id}"},
        },
        "release_task": serialize_task(task),
    }
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.retry_prepare",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    return payload


async def cancel_release_task_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    release_task_id: uuid.UUID,
    expected_version: int,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    task = await repo.get_release_task(
        session,
        organization_id=ctx.organization.id,
        release_task_id=release_task_id,
        for_update=True,
    )
    if task is None:
        raise ValueError("not_found")
    await _require_project(session, ctx, project_id=task.project_id, roles=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.cancel",
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})
    if task.status == "CANCELLED":
        payload = serialize_task(task)
        await repo.create_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="release_task.cancel",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref=payload,
            created_by=ctx.user.id,
            created_at=_now(),
        )
        return payload
    if task.aggregate_version != expected_version:
        raise ValueError("version")
    if task.status not in VALID_CANCEL_SOURCES:
        raise ValueError("state")
    await repo.cas_transition(
        session,
        run=task,
        new_status="CANCELLED",
        expected_status=task.status,
        updated_at=_now(),
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="release_task.cancel",
            resource_type="release_task",
            resource_id=task.id,
            project_id=task.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    payload = serialize_task(task)
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="release_task.cancel",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=_now(),
    )
    return payload


def _prepare_key(organization_id: uuid.UUID, task: ReleaseTask) -> str:
    scope_hash = hashlib.sha256(
        json.dumps(task.scope_snapshot, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()
    return hashlib.sha256(f"{organization_id}:{task.id}:{scope_hash}".encode()).hexdigest()


async def _release_connector_create_item(
    *,
    organization_id: uuid.UUID,
    task: ReleaseTask,
    prepare_key: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """Release connector stub or loopback mock prepare (never production push)."""
    target = await get_loopback_outbound_target(
        session,
        organization_id=organization_id,
        connector_type="release",
    )
    if target is None:
        return {
            "external_system": "release_stub",
            "external_item_id": f"RI-{str(task.id)[:8]}-{prepare_key[:8]}",
        }
    base_url = str(target["base_url"]).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{base_url}/items",
                json={
                    "release_task_id": str(task.id),
                    "prepare_key": prepare_key,
                },
            )
    except httpx.HTTPError as exc:
        raise RuntimeError("release prepare failed") from exc
    if response.status_code != 201:
        raise RuntimeError("release prepare failed")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("release prepare invalid response") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("release prepare invalid response")
    external_system = payload.get("external_system")
    external_item_id = payload.get("external_item_id")
    if not isinstance(external_system, str) or not isinstance(external_item_id, str):
        raise RuntimeError("release prepare missing fields")
    return {
        "external_system": external_system,
        "external_item_id": external_item_id,
    }


async def prepare_after_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    approval_id: uuid.UUID,
    param_hash: str,
    actor_user_id: uuid.UUID | None,
    request_hash: str,
) -> str:
    """Approval execution hook (release_push): PENDING_CONFIRM → SUBMITTED → item."""
    task = await repo.get_release_task(
        session,
        organization_id=organization_id,
        release_task_id=release_task_id,
        for_update=True,
    )
    if task is None:
        return "not_found"
    if task.status != "PENDING_CONFIRM":
        return "state"
    prepare_key = _prepare_key(organization_id, task)
    existing_ref = await repo.get_item_ref_by_prepare_key(
        session,
        organization_id=organization_id,
        prepare_key=prepare_key,
    )
    if existing_ref is None:
        await repo.cas_transition(
            session,
            run=task,
            new_status="SUBMITTED",
            expected_status="PENDING_CONFIRM",
            updated_at=_now(),
        )
    outcome = await _prepare_item(
        session,
        organization_id=organization_id,
        task=task,
        prepare_key=prepare_key,
        actor_user_id=actor_user_id,
        request_hash=request_hash or param_hash,
        action="release_push.prepare",
    )
    return "ok" if outcome in {"created", "idempotent"} else outcome


async def prepare_after_retry(
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Background item preparation after a manual retry (already SUBMITTED)."""
    factory = get_session_factory()
    async with factory() as session:
        task = await repo.get_release_task(
            session,
            organization_id=organization_id,
            release_task_id=release_task_id,
            for_update=True,
        )
        if task is None or task.status != "SUBMITTED":
            await session.commit()
            return
        prepare_key = task.prepare_idempotency_key or _prepare_key(organization_id, task)
        await _prepare_item(
            session,
            organization_id=organization_id,
            task=task,
            prepare_key=prepare_key,
            actor_user_id=actor_user_id,
            request_hash="",
            action="release_task.prepare_retry",
        )
        await session.commit()


async def _prepare_item(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    task: ReleaseTask,
    prepare_key: str,
    actor_user_id: uuid.UUID | None,
    request_hash: str,
    action: str,
) -> str:
    existing_ref = await repo.get_item_ref_by_prepare_key(
        session,
        organization_id=organization_id,
        prepare_key=prepare_key,
    )
    if existing_ref is not None:
        # Idempotent prepare: the external item already exists (AC-067).
        return "idempotent"
    try:
        item = await _release_connector_create_item(
            organization_id=organization_id,
            task=task,
            prepare_key=prepare_key,
            session=session,
        )
    except Exception:
        await repo.cas_transition(
            session,
            run=task,
            new_status="FAILED_RETRYABLE",
            expected_status="SUBMITTED",
            updated_at=_now(),
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action=f"{action}_failed",
                resource_type="release_task",
                resource_id=task.id,
                result="failed",
                request_hash=request_hash,
            ),
        )
        return "prepare_failed"
    scope = dict(task.scope_snapshot)
    scope["release_item"] = {
        "external_system": item["external_system"],
        "external_item_id": item["external_item_id"],
    }
    task.scope_snapshot = scope
    task.prepare_idempotency_key = prepare_key
    await repo.insert_item_ref(
        session,
        organization_id=organization_id,
        release_task_id=task.id,
        external_system=item["external_system"],
        external_item_id=item["external_item_id"],
        prepare_key=prepare_key,
        created_at=_now(),
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type="release_task",
            resource_id=task.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return "created"


async def apply_release_observation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    release_task_id: uuid.UUID,
    external_item_id: str | None,
    request_hash: str,
) -> str:
    """Webhook observation consumer: SUBMITTED → READY; late READY → divergence."""
    task = await repo.get_release_task(
        session,
        organization_id=organization_id,
        release_task_id=release_task_id,
        for_update=True,
    )
    if task is None:
        return "not_found"
    if task.status == "SUBMITTED":
        await repo.cas_transition(
            session,
            run=task,
            new_status="READY",
            expected_status="SUBMITTED",
            updated_at=_now(),
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=organization_id,
                actor_user_id=None,
                action="release_task.ready",
                resource_type="release_task",
                resource_id=task.id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        return "ready"
    if task.status == "CANCELLED":
        divergence = dict(task.divergence or {})
        late_raw = divergence.get("late_ready")
        late: list[dict[str, Any]] = late_raw if isinstance(late_raw, list) else []
        late.append({"external_item_id": external_item_id, "observed_at": _iso(_now())})
        divergence["late_ready"] = late
        task.divergence = divergence
        task.aggregate_version += 1
        await session.flush()
        return "divergence_appended"
    return "ignored"
