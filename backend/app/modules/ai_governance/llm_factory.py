"""LLM factory — the only AI invoke entry point (AC-007 / AC-010)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance import repository as repo
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.quota_governance import query_port as quota_query

VALID_RESULTS = frozenset({"ok", "degraded", "refused"})
DEFAULT_CLASSIFICATION = "Confidential"
ZERO_USAGE: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@dataclass(frozen=True)
class InvokeInput:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    task_type: str
    prompt_version: str
    data_classification: str | None = None
    copilot_session_id: uuid.UUID | None = None
    skill_version_id: uuid.UUID | None = None
    capability_id: str | None = None
    module: str | None = None
    usage_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class InvokeOutput:
    log_id: uuid.UUID
    result: str
    model: str
    usage: dict[str, Any]
    cost: Decimal
    latency_ms: int
    data_classification: str
    refusal_class: str | None = None


def _resolve_model_name(route: Any | None) -> str:
    if route is None:
        return "unrouted"
    allowlist = route.provider_allowlist or []
    if allowlist:
        return str(allowlist[0])
    return "unrouted"


async def _is_kill_switch_active(session: AsyncSession, request: InvokeInput) -> bool:
    controls = await identity_query.get_capability_controls(
        session, organization_id=request.organization_id
    )
    if controls.get("ai_global_tightened") is True:
        return True
    if request.capability_id is not None:
        tightened = [str(item) for item in controls.get("tightened_capabilities", [])]
        if request.capability_id in tightened:
            return True
    if request.module is not None:
        tightened = [str(item) for item in controls.get("tightened_modules", [])]
        if request.module in tightened:
            return True
    return False


async def _log_refused(
    session: AsyncSession,
    *,
    request: InvokeInput,
    started: float,
    log_id: uuid.UUID,
    now: datetime,
    classification: str,
    route: Any | None,
    refusal_class: str,
) -> InvokeOutput:
    latency_ms = int((time.perf_counter() - started) * 1000)
    model_name = _resolve_model_name(route)
    await repo.insert_invocation_log(
        session,
        log_id=log_id,
        organization_id=request.organization_id,
        created_at=now,
        created_by=request.user_id,
        user_id=request.user_id,
        model=model_name,
        prompt_version=request.prompt_version,
        usage=dict(ZERO_USAGE),
        cost=Decimal("0"),
        latency_ms=latency_ms,
        data_classification=classification,
        result="refused",
        model_route_id=route.id if route is not None else None,
        copilot_session_id=request.copilot_session_id,
        skill_version_id=request.skill_version_id,
        input_ref=f"redacted://invocation/{log_id}",
    )
    return InvokeOutput(
        log_id=log_id,
        result="refused",
        model=model_name,
        usage=dict(ZERO_USAGE),
        cost=Decimal("0"),
        latency_ms=latency_ms,
        data_classification=classification,
        refusal_class=refusal_class,
    )


async def invoke(session: AsyncSession, request: InvokeInput) -> InvokeOutput:
    """Resolve route, enforce policy, append AIInvocationLog (no prompt text)."""
    started = time.perf_counter()
    classification = request.data_classification or DEFAULT_CLASSIFICATION
    log_id = uuid.uuid4()
    now = datetime.now(UTC)

    route = await repo.get_model_route_by_task(
        session,
        organization_id=request.organization_id,
        task_type=request.task_type,
        data_classification=classification,
    )

    if await _is_kill_switch_active(session, request):
        return await _log_refused(
            session,
            request=request,
            started=started,
            log_id=log_id,
            now=now,
            classification=classification,
            route=route,
            refusal_class="kill_switch",
        )

    if await quota_query.token_budget_exhausted(session, organization_id=request.organization_id):
        return await _log_refused(
            session,
            request=request,
            started=started,
            log_id=log_id,
            now=now,
            classification=classification,
            route=route,
            refusal_class="quota",
        )

    if classification == "Restricted":
        return await _log_refused(
            session,
            request=request,
            started=started,
            log_id=log_id,
            now=now,
            classification=classification,
            route=route,
            refusal_class="restricted",
        )

    if route is None:
        return await _log_refused(
            session,
            request=request,
            started=started,
            log_id=log_id,
            now=now,
            classification=classification,
            route=None,
            refusal_class="unrouted",
        )

    # M0 stub: no vendor calls; degraded with zero usage.
    latency_ms = int((time.perf_counter() - started) * 1000)
    model_name = _resolve_model_name(route)
    usage: dict[str, Any] = dict(ZERO_USAGE)
    if request.usage_metadata:
        usage.update(request.usage_metadata)
    await repo.insert_invocation_log(
        session,
        log_id=log_id,
        organization_id=request.organization_id,
        created_at=now,
        created_by=request.user_id or request.organization_id,
        user_id=request.user_id,
        model=model_name,
        prompt_version=request.prompt_version,
        usage=usage,
        cost=Decimal("0"),
        latency_ms=latency_ms,
        data_classification=classification,
        result="degraded",
        model_route_id=route.id,
        copilot_session_id=request.copilot_session_id,
        skill_version_id=request.skill_version_id,
        input_ref=f"redacted://invocation/{log_id}",
    )
    return InvokeOutput(
        log_id=log_id,
        result="degraded",
        model=model_name,
        usage=usage,
        cost=Decimal("0"),
        latency_ms=latency_ms,
        data_classification=classification,
    )
