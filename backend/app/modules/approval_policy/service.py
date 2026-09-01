import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.approval_policy import repository as repo
from app.modules.approval_policy.models import ApprovalRequest
from app.modules.approval_policy.policy_gate import (
    ORG_SCOPED_ACTIONS,
    PROJECT_SCOPED_ACTIONS,
    PolicyGate,
    evaluate_policy_gate,
)
from app.modules.execution_registry import command_port as execution_command
from app.modules.identity_tenancy import command_port as identity_command
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext, compute_reauth_required
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

COMMAND_TYPE_ACTION_PREVIEW = "action_preview"
COMMAND_TYPE_APPROVAL_DECISION = "approval_decision"
COMMAND_TYPE_APPROVAL_RESUBMISSION = "approval_resubmission"

VALID_STATUSES = frozenset({"CREATED", "PENDING", "APPROVED", "EXECUTED", "REJECTED", "EXPIRED"})
VALID_ACTION_TYPES = frozenset(
    {
        "jira_write",
        "heal_apply",
        "perf_high_risk",
        "release_push",
        "env_register",
        "agent_tool_action",
        "gate_waiver",
        "kill_switch_restore",
    }
)
VALID_PERSPECTIVES = frozenset({"inbox", "initiated", "all"})

FORBIDDEN_BODY_KEYS = frozenset(
    {"param_hash", "card_payload", "gate", "approval_request_id", "snapshot_ref"}
)

SECRET_KEY_NAMES = frozenset({"password", "secret", "token", "credential_ref"})

ACTION_SUMMARIES: dict[str, str] = {
    "jira_write": "写入 Jira 缺陷",
    "heal_apply": "应用自愈修复",
    "perf_high_risk": "发起高危压测",
    "release_push": "确认 Release 推送",
    "env_register": "注册执行环境",
    "agent_tool_action": "Agent 工具副作用",
    "gate_waiver": "门禁豁免",
    "kill_switch_restore": "恢复能力开关（放开）",
    "copilot_write": "Copilot 写入",
}


@dataclass(frozen=True)
class ActionPreviewInput:
    action_type: str
    target_object_type: str
    target_object_id: uuid.UUID
    payload: dict[str, Any]
    project_id: uuid.UUID | None
    expected_target_version: int | None


def compute_param_hash(
    *,
    action_type: str,
    target_object_type: str,
    target_object_id: uuid.UUID,
    project_id: uuid.UUID | None,
    payload: dict[str, Any],
    expected_target_version: int | None,
) -> str:
    canonical: dict[str, Any] = {
        "action_type": action_type,
        "payload": payload,
        "target_object_id": str(target_object_id),
        "target_object_type": target_object_type,
    }
    if project_id is not None:
        canonical["project_id"] = str(project_id)
    if expected_target_version is not None:
        canonical["expected_target_version"] = expected_target_version
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if key in SECRET_KEY_NAMES:
            redacted[key] = "[redacted]"
        elif isinstance(value, dict):
            redacted[key] = _redact_payload(value)
        else:
            redacted[key] = value
    return redacted


def build_card_payload(
    *,
    action_type: str,
    target_object_type: str,
    target_object_id: uuid.UUID,
    payload: dict[str, Any],
    side_effect_level: str,
    param_hash: str,
) -> dict[str, Any]:
    summary = ACTION_SUMMARIES.get(action_type, action_type)
    return {
        "action": {
            "action_type": action_type,
            "summary": summary,
            "payload_redacted": _redact_payload(payload),
        },
        "resource": {
            "target_object_type": target_object_type,
            "target_object_id": str(target_object_id),
            "display_name": f"{target_object_type}:{target_object_id}",
        },
        "diff": {
            "before": None,
            "after": None,
            "summary": "",
        },
        "data_source": {
            "evidence_refs": [],
            "source_summary": "Policy Gate Preview",
        },
        "model_and_skill_version": {
            "model": None,
            "prompt_version": None,
            "skill_version_id": None,
        },
        "risk_level": {
            "side_effect_level": side_effect_level,
            "rationale": f"Frozen action level for {action_type}",
        },
        "cost_estimate": {
            "amount": None,
            "unit": None,
            "unknown_reason": "Preview only; execution cost not estimated",
        },
        "rollback": {
            "capability": "none",
            "snapshot_ref": None,
            "compensation_summary": None,
            "none_declared": True,
        },
        "param_hash": param_hash,
    }


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def build_preview_payload(
    *,
    preview_id: uuid.UUID,
    action_type: str,
    gate: PolicyGate,
    param_hash: str,
    card_payload: dict[str, Any],
    side_effect_level: str,
    created_at: datetime,
    target_object_type: str,
    target_object_id: uuid.UUID,
    expected_target_version: int | None,
    approval_request_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "preview_id": str(preview_id),
        "action_type": action_type,
        "gate": gate.value,
        "param_hash": param_hash,
        "card_payload": card_payload,
        "side_effect_level": side_effect_level,
        "created_at": _iso(created_at),
        "target": {
            "object_type": target_object_type,
            "object_id": str(target_object_id),
        },
    }
    if expected_target_version is not None:
        payload["target"]["version"] = expected_target_version
    if approval_request_id is not None:
        payload["approval_request_id"] = str(approval_request_id)
        payload["bound_hash"] = param_hash
    return payload


def _validate_payload_secrets(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if key in SECRET_KEY_NAMES and isinstance(value, str) and value.strip():
            raise ValueError("validation")
        if isinstance(value, dict):
            _validate_payload_secrets(value)


async def create_action_preview(
    session: AsyncSession,
    ctx: SessionContext,
    settings: Settings,
    *,
    preview_input: ActionPreviewInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    user_id = ctx.user.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_ACTION_PREVIEW,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    action_type = preview_input.action_type
    project_id = preview_input.project_id

    if action_type in PROJECT_SCOPED_ACTIONS and project_id is None:
        raise ValueError("validation")

    if action_type in ORG_SCOPED_ACTIONS and project_id is not None:
        raise ValueError("validation")

    if project_id is not None:
        if not await identity_query.project_exists_in_org(
            session, organization_id=org_id, project_id=project_id
        ):
            raise ValueError("not_found")
        role = await identity_query.get_project_membership_role(
            session,
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
        )
        if role is None:
            raise ValueError("not_found")
        if role == "viewer":
            raise ValueError("forbidden")
    elif not await identity_query.caller_has_non_viewer_role(
        session, organization_id=org_id, user_id=user_id
    ):
        raise ValueError("forbidden")

    reauth_required = compute_reauth_required(
        ctx.session, reauth_window_seconds=settings.reauth_window_seconds, now=now
    )
    gate_result = evaluate_policy_gate(
        action_type=action_type,
        payload=preview_input.payload,
        reauth_required=reauth_required,
    )
    preview_id = uuid.uuid4()
    audit_base = AuditAppendInput(
        organization_id=org_id,
        actor_user_id=user_id,
        action="action_preview",
        resource_type="action_preview",
        resource_id=preview_id,
        project_id=project_id,
        request_hash=request_hash,
    )

    if gate_result.deny_reason == "state":
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=audit_base.organization_id,
                actor_user_id=audit_base.actor_user_id,
                action=audit_base.action,
                resource_type=audit_base.resource_type,
                resource_id=audit_base.resource_id,
                project_id=audit_base.project_id,
                request_hash=audit_base.request_hash,
                result="failed",
            ),
        )
        raise ValueError("state")

    if gate_result.gate == PolicyGate.DENY:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=audit_base.organization_id,
                actor_user_id=audit_base.actor_user_id,
                action=audit_base.action,
                resource_type=audit_base.resource_type,
                resource_id=audit_base.resource_id,
                project_id=audit_base.project_id,
                request_hash=audit_base.request_hash,
                result="failed",
            ),
        )
        if gate_result.deny_reason == "undeclared":
            raise ValueError("policy_undeclared")
        raise ValueError("policy_deny")

    if gate_result.gate == PolicyGate.REQUIRE_REAUTH:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=audit_base.organization_id,
                actor_user_id=audit_base.actor_user_id,
                action=audit_base.action,
                resource_type=audit_base.resource_type,
                resource_id=audit_base.resource_id,
                project_id=audit_base.project_id,
                request_hash=audit_base.request_hash,
                result="failed",
            ),
        )
        raise ValueError("require_reauth")

    side_effect_level = gate_result.side_effect_level
    if side_effect_level is None:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=audit_base.organization_id,
                actor_user_id=audit_base.actor_user_id,
                action=audit_base.action,
                resource_type=audit_base.resource_type,
                resource_id=audit_base.resource_id,
                project_id=audit_base.project_id,
                request_hash=audit_base.request_hash,
                result="failed",
            ),
        )
        raise ValueError("state")

    param_hash = compute_param_hash(
        action_type=action_type,
        target_object_type=preview_input.target_object_type,
        target_object_id=preview_input.target_object_id,
        project_id=project_id,
        payload=preview_input.payload,
        expected_target_version=preview_input.expected_target_version,
    )
    card_payload = build_card_payload(
        action_type=action_type,
        target_object_type=preview_input.target_object_type,
        target_object_id=preview_input.target_object_id,
        payload=preview_input.payload,
        side_effect_level=side_effect_level,
        param_hash=param_hash,
    )

    approval_request_id: uuid.UUID | None = None
    if gate_result.gate == PolicyGate.REQUIRE_APPROVAL:
        if project_id is not None:
            candidates = await identity_query.list_project_owner_admin_user_ids(
                session,
                organization_id=org_id,
                project_id=project_id,
                exclude_user_id=user_id,
            )
        else:
            candidates = await identity_query.list_org_owner_admin_user_ids(
                session,
                organization_id=org_id,
                exclude_user_id=user_id,
            )
        if not candidates:
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=audit_base.organization_id,
                    actor_user_id=audit_base.actor_user_id,
                    action=audit_base.action,
                    resource_type=audit_base.resource_type,
                    resource_id=audit_base.resource_id,
                    project_id=audit_base.project_id,
                    request_hash=audit_base.request_hash,
                    result="failed",
                ),
            )
            raise ValueError("state")

        approval = await repo.create_approval_request(
            session,
            organization_id=org_id,
            created_at=now,
            created_by=user_id,
            action_type=action_type,
            target_object_type=preview_input.target_object_type,
            target_object_id=preview_input.target_object_id,
            action_payload=preview_input.payload,
            param_hash=param_hash,
            card_payload=card_payload,
            side_effect_level=side_effect_level,
            initiator_id=user_id,
            approver_id=candidates[0],
            expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
            project_id=project_id,
            expected_target_version=preview_input.expected_target_version,
        )
        approval_request_id = approval.id

    response = build_preview_payload(
        preview_id=preview_id,
        action_type=action_type,
        gate=gate_result.gate,
        param_hash=param_hash,
        card_payload=card_payload,
        side_effect_level=side_effect_level,
        created_at=now,
        target_object_type=preview_input.target_object_type,
        target_object_id=preview_input.target_object_id,
        expected_target_version=preview_input.expected_target_version,
        approval_request_id=approval_request_id,
    )

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=audit_base.organization_id,
            actor_user_id=audit_base.actor_user_id,
            action=audit_base.action,
            resource_type=audit_base.resource_type,
            resource_id=audit_base.resource_id,
            project_id=audit_base.project_id,
            request_hash=audit_base.request_hash,
            result="ok",
        ),
    )
    await repo.create_action_preview_record(
        session,
        preview_id=preview_id,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
        preview_payload=response,
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_ACTION_PREVIEW,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=user_id,
        created_at=now,
    )
    return response


def _serialize_approval_item(approval: ApprovalRequest, *, caller_id: uuid.UUID) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(approval.id),
        "action_type": approval.action_type,
        "target_object_type": approval.target_object_type,
        "target_object_id": str(approval.target_object_id),
        "param_hash": approval.param_hash,
        "card_payload": approval.card_payload,
        "status": approval.status,
        "initiator_id": str(approval.initiator_id),
        "expires_at": _iso(approval.expires_at),
        "side_effect_level": approval.side_effect_level,
        "version": approval.aggregate_version,
        "four_eyes_self": caller_id == approval.initiator_id,
        "created_at": _iso(approval.created_at),
        "updated_at": _iso(approval.updated_at),
    }
    if approval.approver_id is not None:
        item["approver_id"] = str(approval.approver_id)
    if approval.escalate_to is not None:
        item["escalate_to"] = str(approval.escalate_to)
    if approval.expired_reason is not None:
        item["expired_reason"] = approval.expired_reason
    if approval.origin_request_id is not None:
        item["origin_request_id"] = str(approval.origin_request_id)
    if approval.status == "EXECUTED" and approval.execution_result is not None:
        item["execution_result"] = approval.execution_result
    return item


def _serialize_approval_detail(
    approval: ApprovalRequest, *, caller_id: uuid.UUID
) -> dict[str, Any]:
    detail = _serialize_approval_item(approval, caller_id=caller_id)
    detail["action_payload_redacted"] = _redact_payload(approval.action_payload)
    if approval.snapshot_ref is not None:
        detail["snapshot_ref"] = approval.snapshot_ref
    if approval.original_initiator_id is not None:
        detail["original_initiator_id"] = str(approval.original_initiator_id)
    return detail


async def _lazy_expire_if_needed(
    session: AsyncSession,
    approval: ApprovalRequest,
    *,
    now: datetime,
) -> None:
    if approval.status == "PENDING" and now > approval.expires_at:
        approval.status = "EXPIRED"
        approval.expired_reason = "ttl"
        approval.updated_at = now
        approval.aggregate_version += 1
        await session.flush()


async def _can_view_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    caller_id: uuid.UUID,
    approval: ApprovalRequest,
    memberships: list[tuple[uuid.UUID, str]],
) -> bool:
    if approval.initiator_id == caller_id:
        return True
    if approval.approver_id == caller_id or approval.escalate_to == caller_id:
        return True
    roles = {role for _, role in memberships}
    if "owner" in roles or "admin" in roles:
        return True
    if "viewer" in roles or "tester" in roles:
        return await identity_query.users_share_project(
            session,
            organization_id=organization_id,
            user_id_a=caller_id,
            user_id_b=approval.initiator_id,
        )
    return False


def _build_visibility_filter(
    *,
    caller_id: uuid.UUID,
    perspective: str,
    is_owner_admin: bool,
) -> Any | None:
    if perspective == "initiated":
        return ApprovalRequest.initiator_id == caller_id
    if perspective == "inbox":
        return and_(
            ApprovalRequest.status == "PENDING",
            or_(
                ApprovalRequest.approver_id == caller_id,
                ApprovalRequest.escalate_to == caller_id,
            ),
        )
    if is_owner_admin:
        return None
    return or_(
        ApprovalRequest.initiator_id == caller_id,
        ApprovalRequest.approver_id == caller_id,
        ApprovalRequest.escalate_to == caller_id,
    )


async def list_approval_requests_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    status: str | None,
    action_type: str | None,
    perspective: str | None,
    project_id: uuid.UUID | None,
    target_object_id: uuid.UUID | None,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    caller_id = ctx.user.id
    now = datetime.now(UTC)

    if limit is not None and limit < 1:
        raise ValueError("validation")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("validation")
    if action_type is not None and action_type not in VALID_ACTION_TYPES:
        raise ValueError("validation")
    perspective_value = perspective or "all"
    if perspective_value not in VALID_PERSPECTIVES:
        raise ValueError("validation")

    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=org_id, user_id=caller_id
    )
    if not memberships:
        raise ValueError("forbidden")

    if project_id is not None and not any(pid == project_id for pid, _ in memberships):
        raise ValueError("not_found")

    is_owner_admin = await identity_query.caller_is_owner_or_admin(
        session, organization_id=org_id, user_id=caller_id
    )

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    visibility = _build_visibility_filter(
        caller_id=caller_id,
        perspective=perspective_value,
        is_owner_admin=is_owner_admin,
    )

    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_approval_requests(
        session,
        organization_id=org_id,
        status=status,
        action_type=action_type,
        target_object_id=target_object_id,
        project_id=project_id,
        visibility_filter=visibility,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        fetch_limit=fetch_limit,
        now=now,
    )

    visible: list[ApprovalRequest] = []
    for row in rows:
        if is_owner_admin or await _can_view_approval(
            session,
            organization_id=org_id,
            caller_id=caller_id,
            approval=row,
            memberships=memberships,
        ):
            await _lazy_expire_if_needed(session, row, now=now)
            if status is not None and row.status != status:
                continue
            if perspective_value == "inbox" and row.status != "PENDING":
                continue
            visible.append(row)

    has_more = False
    if limit is not None and len(visible) > limit:
        has_more = True
        visible = visible[:limit]

    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = repo.encode_created_id_cursor(created_at=last.created_at, item_id=last.id)

    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    if limit is not None:
        page["limit"] = limit

    return {
        "items": [_serialize_approval_item(item, caller_id=caller_id) for item in visible],
        "page": page,
    }


async def get_approval_request_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    approval_request_id: uuid.UUID,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    caller_id = ctx.user.id
    now = datetime.now(UTC)

    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=org_id, user_id=caller_id
    )
    if not memberships:
        raise ValueError("not_found")

    approval = await repo.get_approval_request(
        session, organization_id=org_id, approval_request_id=approval_request_id
    )
    if approval is None:
        raise ValueError("not_found")
    if not await _can_view_approval(
        session,
        organization_id=org_id,
        caller_id=caller_id,
        approval=approval,
        memberships=memberships,
    ):
        raise ValueError("not_found")

    await _lazy_expire_if_needed(session, approval, now=now)
    return _serialize_approval_detail(approval, caller_id=caller_id)


async def get_action_preview_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    preview_id: uuid.UUID,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    now = datetime.now(UTC)
    record = await repo.get_action_preview_record(
        session, organization_id=org_id, preview_id=preview_id
    )
    if record is None:
        raise ValueError("not_found")
    if now > record.expires_at:
        raise ValueError("approval_expired")
    return dict(record.preview_payload)


def _caller_can_decide(caller_id: uuid.UUID, approval: ApprovalRequest) -> bool:
    return caller_id == approval.approver_id or caller_id == approval.escalate_to


async def submit_approval_decision(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    approval_request_id: uuid.UUID,
    decision: str,
    reason: str | None,
    expected_version: int,
    idempotency_key: str | None,
    request_hash: str | None,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    caller_id = ctx.user.id
    now = datetime.now(UTC)

    if decision not in {"approve", "reject"}:
        raise ValueError("validation")
    if decision == "reject" and (reason is None or not reason.strip()):
        raise ValueError("validation")
    if expected_version < 1:
        raise ValueError("validation")

    if idempotency_key is not None and request_hash is not None:
        existing = await repo.get_idempotency_record(
            session,
            organization_id=org_id,
            command_type=COMMAND_TYPE_APPROVAL_DECISION,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ValueError("idempotency_conflict")
            if existing.response_ref is not None:
                return existing.response_ref

    is_owner_admin = await identity_query.caller_is_owner_or_admin(
        session, organization_id=org_id, user_id=caller_id
    )
    if not is_owner_admin:
        raise ValueError("forbidden")

    approval = await repo.get_approval_request(
        session,
        organization_id=org_id,
        approval_request_id=approval_request_id,
        for_update=True,
    )
    if approval is None:
        raise ValueError("not_found")

    await _lazy_expire_if_needed(session, approval, now=now)

    if approval.status == "EXPIRED":
        raise ValueError("approval_expired")
    if approval.status != "PENDING":
        raise ValueError("state")

    if approval.aggregate_version != expected_version:
        raise ValueError("version")

    if caller_id == approval.initiator_id:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=org_id,
                actor_user_id=caller_id,
                action="approval_decision",
                resource_type="approval_request",
                resource_id=approval.id,
                project_id=approval.project_id,
                request_hash=request_hash,
                result="failed",
            ),
        )
        raise ValueError("four_eyes")

    if not _caller_can_decide(caller_id, approval):
        raise ValueError("forbidden")

    recomputed = compute_param_hash(
        action_type=approval.action_type,
        target_object_type=approval.target_object_type,
        target_object_id=approval.target_object_id,
        project_id=approval.project_id,
        payload=approval.action_payload,
        expected_target_version=approval.expected_target_version,
    )
    if recomputed != approval.param_hash:
        approval.status = "EXPIRED"
        approval.expired_reason = "invalidated"
        approval.updated_at = now
        approval.aggregate_version += 1
        await session.flush()
        raise ValueError("param_hash")

    if decision == "approve":
        approval.status = "APPROVED"
        approval.approver_id = caller_id
    else:
        approval.status = "REJECTED"
        approval.approver_id = caller_id

    approval.updated_at = now
    approval.aggregate_version += 1
    await session.flush()

    if decision == "approve" and approval.action_type == "kill_switch_restore":
        target = approval.action_payload.get("target")
        if isinstance(target, dict):
            try:
                await identity_command.apply_kill_switch_restore(
                    session,
                    organization_id=org_id,
                    target=target,
                )
                approval.status = "EXECUTED"
                approval.execution_result = "ok"
                approval.updated_at = datetime.now(UTC)
                approval.aggregate_version += 1
                await session.flush()
                await append_audit_event(
                    session,
                    AuditAppendInput(
                        organization_id=org_id,
                        actor_user_id=caller_id,
                        action="kill_switch_restore",
                        resource_type="organization",
                        resource_id=approval.target_object_id,
                        request_hash=request_hash,
                        result="ok",
                    ),
                )
            except ValueError:
                pass

    if decision == "approve" and approval.action_type == "env_register":
        try:
            await execution_command.activate_after_env_register(
                session,
                organization_id=org_id,
                environment_id=approval.target_object_id,
            )
            approval.status = "EXECUTED"
            approval.execution_result = "ok"
            approval.updated_at = datetime.now(UTC)
            approval.aggregate_version += 1
            await session.flush()
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=org_id,
                    actor_user_id=caller_id,
                    action="env_register",
                    resource_type="execution_environment",
                    resource_id=approval.target_object_id,
                    project_id=approval.project_id,
                    request_hash=request_hash,
                    result="ok",
                ),
            )
        except ValueError:
            pass

    response = _serialize_approval_item(approval, caller_id=caller_id)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=caller_id,
            action="approval_decision",
            resource_type="approval_request",
            resource_id=approval.id,
            project_id=approval.project_id,
            request_hash=request_hash,
            result="ok",
        ),
    )
    if idempotency_key is not None and request_hash is not None:
        await repo.create_idempotency_record(
            session,
            organization_id=org_id,
            command_type=COMMAND_TYPE_APPROVAL_DECISION,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref=response,
            created_by=caller_id,
            created_at=now,
        )
    return response


async def resubmit_approval_request(
    session: AsyncSession,
    ctx: SessionContext,
    settings: Settings,
    *,
    approval_request_id: uuid.UUID,
    payload: dict[str, Any],
    expected_target_version: int | None,
    expected_origin_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    caller_id = ctx.user.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_APPROVAL_RESUBMISSION,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    origin = await repo.get_approval_request(
        session,
        organization_id=org_id,
        approval_request_id=approval_request_id,
        for_update=True,
    )
    if origin is None:
        raise ValueError("not_found")

    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=org_id, user_id=caller_id
    )
    if not memberships or all(role == "viewer" for _, role in memberships):
        raise ValueError("forbidden")

    is_initiator = origin.initiator_id == caller_id
    can_initiate = is_initiator or await identity_query.caller_has_non_viewer_role(
        session, organization_id=org_id, user_id=caller_id
    )
    if not can_initiate:
        raise ValueError("forbidden")

    await _lazy_expire_if_needed(session, origin, now=now)

    if expected_origin_version is not None and origin.aggregate_version != expected_origin_version:
        raise ValueError("version")

    allowed_origin = origin.status in {"PENDING", "EXPIRED", "REJECTED"} or (
        origin.status == "EXECUTED" and origin.execution_result in {"failed", "unknown"}
    )
    if not allowed_origin:
        raise ValueError("state")

    if origin.status == "APPROVED":
        raise ValueError("state")

    project_id = origin.project_id
    if project_id is not None:
        role = await identity_query.get_project_membership_role(
            session,
            organization_id=org_id,
            project_id=project_id,
            user_id=caller_id,
        )
        if role is None:
            raise ValueError("not_found")
        if role == "viewer":
            raise ValueError("forbidden")

    try:
        _validate_payload_secrets(payload)
    except ValueError:
        raise ValueError("validation") from None

    reauth_required = compute_reauth_required(
        ctx.session, reauth_window_seconds=settings.reauth_window_seconds, now=now
    )
    gate_result = evaluate_policy_gate(
        action_type=origin.action_type,
        payload=payload,
        reauth_required=reauth_required,
    )

    if gate_result.gate == PolicyGate.DENY:
        if gate_result.deny_reason == "undeclared":
            raise ValueError("policy_undeclared")
        raise ValueError("policy_deny")
    if gate_result.gate == PolicyGate.REQUIRE_REAUTH:
        raise ValueError("require_reauth")
    if gate_result.gate == PolicyGate.ALLOW:
        raise ValueError("state")

    side_effect_level = gate_result.side_effect_level
    if side_effect_level is None:
        raise ValueError("state")

    target_version = (
        expected_target_version
        if expected_target_version is not None
        else origin.expected_target_version
    )
    param_hash = compute_param_hash(
        action_type=origin.action_type,
        target_object_type=origin.target_object_type,
        target_object_id=origin.target_object_id,
        project_id=project_id,
        payload=payload,
        expected_target_version=target_version,
    )
    card_payload = build_card_payload(
        action_type=origin.action_type,
        target_object_type=origin.target_object_type,
        target_object_id=origin.target_object_id,
        payload=payload,
        side_effect_level=side_effect_level,
        param_hash=param_hash,
    )

    if project_id is not None:
        candidates = await identity_query.list_project_owner_admin_user_ids(
            session,
            organization_id=org_id,
            project_id=project_id,
            exclude_user_id=caller_id,
        )
    else:
        candidates = await identity_query.list_org_owner_admin_user_ids(
            session,
            organization_id=org_id,
            exclude_user_id=caller_id,
        )
    if not candidates:
        raise ValueError("state")

    origin_final_status = origin.status
    if origin.status == "PENDING":
        origin.status = "EXPIRED"
        origin.expired_reason = "withdrawn"
        origin.updated_at = now
        origin.aggregate_version += 1
        origin_final_status = "EXPIRED"

    original_initiator = origin.original_initiator_id or origin.initiator_id
    new_approval = await repo.create_approval_request(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=caller_id,
        action_type=origin.action_type,
        target_object_type=origin.target_object_type,
        target_object_id=origin.target_object_id,
        action_payload=payload,
        param_hash=param_hash,
        card_payload=card_payload,
        side_effect_level=side_effect_level,
        initiator_id=caller_id,
        approver_id=candidates[0],
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
        project_id=project_id,
        expected_target_version=target_version,
        origin_request_id=origin.id,
        original_initiator_id=original_initiator,
    )

    response = {
        "origin_request_id": str(origin.id),
        "origin_final_status": origin_final_status,
        "new_approval_request": _serialize_approval_item(new_approval, caller_id=caller_id),
    }
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=caller_id,
            action="approval_resubmission",
            resource_type="approval_request",
            resource_id=new_approval.id,
            project_id=project_id,
            request_hash=request_hash,
            result="ok",
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_APPROVAL_RESUBMISSION,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=caller_id,
        created_at=now,
    )
    return response
