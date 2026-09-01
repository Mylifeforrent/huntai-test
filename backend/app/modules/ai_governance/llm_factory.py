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


@dataclass(frozen=True)
class InvokeOutput:
    log_id: uuid.UUID
    result: str
    model: str
    usage: dict[str, Any]
    cost: Decimal
    latency_ms: int
    data_classification: str


def _resolve_model_name(route: Any | None) -> str:
    if route is None:
        return "unrouted"
    allowlist = route.provider_allowlist or []
    if allowlist:
        return str(allowlist[0])
    return "unrouted"


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

    if classification == "Restricted":
        latency_ms = int((time.perf_counter() - started) * 1000)
        await repo.insert_invocation_log(
            session,
            log_id=log_id,
            organization_id=request.organization_id,
            created_at=now,
            created_by=request.user_id,
            user_id=request.user_id,
            model=_resolve_model_name(route),
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
            model=_resolve_model_name(route),
            usage=dict(ZERO_USAGE),
            cost=Decimal("0"),
            latency_ms=latency_ms,
            data_classification=classification,
        )

    if route is None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        await repo.insert_invocation_log(
            session,
            log_id=log_id,
            organization_id=request.organization_id,
            created_at=now,
            created_by=request.user_id,
            user_id=request.user_id,
            model="unrouted",
            prompt_version=request.prompt_version,
            usage=dict(ZERO_USAGE),
            cost=Decimal("0"),
            latency_ms=latency_ms,
            data_classification=classification,
            result="refused",
            copilot_session_id=request.copilot_session_id,
            skill_version_id=request.skill_version_id,
            input_ref=f"redacted://invocation/{log_id}",
        )
        return InvokeOutput(
            log_id=log_id,
            result="refused",
            model="unrouted",
            usage=dict(ZERO_USAGE),
            cost=Decimal("0"),
            latency_ms=latency_ms,
            data_classification=classification,
        )

    # M0 stub: no vendor calls; degraded with zero usage.
    latency_ms = int((time.perf_counter() - started) * 1000)
    model_name = _resolve_model_name(route)
    await repo.insert_invocation_log(
        session,
        log_id=log_id,
        organization_id=request.organization_id,
        created_at=now,
        created_by=request.user_id or request.organization_id,
        user_id=request.user_id,
        model=model_name,
        prompt_version=request.prompt_version,
        usage=dict(ZERO_USAGE),
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
        usage=dict(ZERO_USAGE),
        cost=Decimal("0"),
        latency_ms=latency_ms,
        data_classification=classification,
    )
