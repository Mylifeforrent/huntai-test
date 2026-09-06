"""Cross-module commands for approval_policy (no ORM export to consumers)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.approval_policy import repository as repo
from app.modules.approval_policy.models import ApprovalRequest
from app.modules.approval_policy.policy_gate import resolve_side_effect_level
from app.modules.approval_policy.service import (
    build_card_payload,
    compute_param_hash,
)
from app.modules.identity_tenancy import query_port as identity_query


async def create_env_register_approval(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    project_id: uuid.UUID,
    target_environment_id: uuid.UUID,
    gate_payload: dict[str, Any],
    initiator_id: uuid.UUID,
) -> uuid.UUID:
    """Create a four-eyes approval for env_register bound to a concrete environment."""
    now = datetime.now(UTC)
    candidates = await identity_query.list_project_owner_admin_user_ids(
        session,
        organization_id=organization_id,
        project_id=project_id,
        exclude_user_id=initiator_id,
    )
    if not candidates:
        raise ValueError("state")

    side_effect_level = resolve_side_effect_level("env_register", gate_payload)
    if side_effect_level is None:
        raise ValueError("policy_undeclared")

    param_hash = compute_param_hash(
        action_type="env_register",
        target_object_type="execution_environment",
        target_object_id=target_environment_id,
        project_id=project_id,
        payload=gate_payload,
        expected_target_version=None,
    )
    card_payload = build_card_payload(
        action_type="env_register",
        target_object_type="execution_environment",
        target_object_id=target_environment_id,
        payload=gate_payload,
        side_effect_level=side_effect_level,
        param_hash=param_hash,
    )
    card_payload["resource"]["display_name"] = gate_payload.get("name", str(target_environment_id))

    approval = await repo.create_approval_request(
        session,
        organization_id=organization_id,
        created_at=now,
        created_by=created_by,
        action_type="env_register",
        target_object_type="execution_environment",
        target_object_id=target_environment_id,
        action_payload=gate_payload,
        param_hash=param_hash,
        card_payload=card_payload,
        side_effect_level=side_effect_level,
        initiator_id=initiator_id,
        approver_id=candidates[0],
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
        project_id=project_id,
        expected_target_version=None,
    )
    return approval.id


async def find_pending_perf_high_risk(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> uuid.UUID | None:
    result = await session.execute(
        select(ApprovalRequest.id).where(
            ApprovalRequest.organization_id == organization_id,
            ApprovalRequest.action_type == "perf_high_risk",
            ApprovalRequest.target_object_type == "TestRun",
            ApprovalRequest.target_object_id == test_run_id,
            ApprovalRequest.status == "PENDING",
        )
    )
    return result.scalar_one_or_none()


async def create_perf_high_risk_approval(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    project_id: uuid.UUID,
    test_run_id: uuid.UUID,
    scenario: dict[str, Any],
    approval_hash: str,
) -> tuple[uuid.UUID, str]:
    """Create the perf_high_risk approval; returns (approval_id, param_hash)."""
    initiator = created_by
    if initiator is None:
        raise ValueError("state")
    candidates = await identity_query.list_project_owner_admin_user_ids(
        session,
        organization_id=organization_id,
        project_id=project_id,
        exclude_user_id=initiator,
    )
    if not candidates:
        raise ValueError("state")
    now = datetime.now(UTC)
    payload = {"scenario": scenario, "test_run_id": str(test_run_id)}
    param_hash = compute_param_hash(
        action_type="perf_high_risk",
        target_object_type="TestRun",
        target_object_id=test_run_id,
        project_id=project_id,
        payload=payload,
        expected_target_version=None,
    )
    card_payload = build_card_payload(
        action_type="perf_high_risk",
        target_object_type="TestRun",
        target_object_id=test_run_id,
        payload=payload,
        side_effect_level="L3",
        param_hash=param_hash,
    )
    row = await repo.create_approval_request(
        session,
        organization_id=organization_id,
        created_at=now,
        created_by=initiator,
        action_type="perf_high_risk",
        target_object_type="TestRun",
        target_object_id=test_run_id,
        action_payload=payload,
        param_hash=param_hash,
        card_payload=card_payload,
        side_effect_level="L3",
        initiator_id=initiator,
        approver_id=candidates[0],
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
        project_id=project_id,
        expected_target_version=None,
    )
    return row.id, param_hash
