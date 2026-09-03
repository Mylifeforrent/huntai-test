from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.models import QualityGatePolicy
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin"})

VALID_MODES = frozenset({"report_only", "blocking"})
REQUIRED_THRESHOLD_KEYS = frozenset({"min_pass_rate", "max_p95_ms", "max_error_rate"})

COMMAND_CREATE = "quality_gate_policy.create"
COMMAND_PATCH = "quality_gate_policy.patch"


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _is_json_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def _validate_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(thresholds, dict):
        raise ValueError("validation")
    keys = set(thresholds.keys())
    if keys != REQUIRED_THRESHOLD_KEYS:
        raise ValueError("validation")
    for key in REQUIRED_THRESHOLD_KEYS:
        if not _is_json_number(thresholds[key]):
            raise ValueError("validation")
    return thresholds


async def _require_project_role(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    allowed: frozenset[str],
) -> str:
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
    return role


def serialize_list_item(row: QualityGatePolicy) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "thresholds": dict(row.thresholds),
        "mode": row.mode,
        "policy_version": row.policy_version,
        "version": row.aggregate_version,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def serialize_detail(row: QualityGatePolicy) -> dict[str, Any]:
    payload = serialize_list_item(row)
    payload["scope"] = dict(row.scope)
    return payload


@dataclass(frozen=True)
class PolicyCreateInput:
    project_id: uuid.UUID
    thresholds: dict[str, Any]
    mode: str
    scope: dict[str, Any]
    confirm_blocking: bool | None = None


@dataclass(frozen=True)
class PolicyPatchInput:
    expected_version: int
    thresholds: dict[str, Any] | None = None
    mode: str | None = None
    scope: dict[str, Any] | None = None
    confirm_blocking: bool | None = None


async def list_policies_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    cursor: str | None = None,
    limit: int | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=project_id, allowed=READ_ROLES)
    if mode is not None and mode not in VALID_MODES:
        raise ValueError("validation")
    page_limit = min(limit or 50, 100)
    cursor_updated_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_updated_at, cursor_id = repo.decode_updated_id_cursor(cursor)
    rows = await repo.list_policies(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        mode=mode,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
        limit=page_limit,
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = repo.encode_updated_id_cursor(updated_at=last.updated_at, item_id=last.id)
    return {
        "items": [serialize_list_item(row) for row in items],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_policy_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    policy_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_policy(
        session,
        organization_id=ctx.organization.id,
        policy_id=policy_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    return serialize_detail(row)


async def create_policy_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: PolicyCreateInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=body.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if body.mode not in VALID_MODES:
        raise ValueError("validation")
    if body.mode == "blocking" and body.confirm_blocking is not True:
        raise ValueError("validation")
    if not isinstance(body.scope, dict):
        raise ValueError("validation")
    thresholds = _validate_thresholds(body.thresholds)

    now = datetime.now(UTC)
    policy_id = uuid.uuid4()
    row = QualityGatePolicy(
        id=policy_id,
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        aggregate_version=1,
        project_id=body.project_id,
        thresholds=thresholds,
        mode=body.mode,
        scope=dict(body.scope),
        policy_version=1,
    )
    await repo.insert_policy(session, row)
    response = {"data": serialize_detail(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE,
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
            action="quality_gate_policy.create",
            resource_type="quality_gate_policy",
            resource_id=policy_id,
            project_id=body.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def patch_policy_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    policy_id: uuid.UUID,
    body: PolicyPatchInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_policy(
        session,
        organization_id=ctx.organization.id,
        policy_id=policy_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PATCH,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.aggregate_version != body.expected_version:
        raise ValueError("version")

    next_mode = body.mode if body.mode is not None else row.mode
    if next_mode not in VALID_MODES:
        raise ValueError("validation")
    if next_mode == "blocking" and row.mode != "blocking" and body.confirm_blocking is not True:
        raise ValueError("validation")

    now = datetime.now(UTC)
    content_changed = False
    if body.thresholds is not None:
        row.thresholds = _validate_thresholds(body.thresholds)
        content_changed = True
    if body.mode is not None:
        row.mode = body.mode
        content_changed = True
    if body.scope is not None:
        if not isinstance(body.scope, dict):
            raise ValueError("validation")
        row.scope = dict(body.scope)
        content_changed = True

    row.aggregate_version += 1
    row.updated_at = now
    if content_changed:
        row.policy_version += 1

    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PATCH,
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
            action="quality_gate_policy.patch",
            resource_type="quality_gate_policy",
            resource_id=policy_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response
