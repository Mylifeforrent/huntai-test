import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.approval_policy import repository as repo
from app.modules.approval_policy.policy_gate import (
    ORG_SCOPED_ACTIONS,
    PROJECT_SCOPED_ACTIONS,
    PolicyGate,
    evaluate_policy_gate,
)
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext, compute_reauth_required
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

COMMAND_TYPE_ACTION_PREVIEW = "action_preview"

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
