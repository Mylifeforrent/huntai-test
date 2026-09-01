import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance import repository as repo
from app.modules.ai_governance.models import AIInvocationLog, ModelRoute
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

COMMAND_TYPE_MODEL_ROUTE_PUT = "model_route.put"
COMMAND_TYPE_CONNECTION_TEST = "model_route.connection_test"

DATA_CLASSIFICATIONS = frozenset({"Public", "Internal", "Confidential", "Restricted"})
LOCAL_PROVIDERS = frozenset({"local", "local-only"})
INVOCATION_RESULTS = frozenset({"ok", "degraded", "refused"})

DEFAULT_TASK_TYPE = "general"


@dataclass(frozen=True)
class ModelRoutePutInput:
    expected_version: int
    task_type: str
    data_classification: str
    provider_allowlist: list[str]
    max_cost: Decimal
    fallback: dict[str, Any] | None
    require_prompt_version: bool
    require_structured_output: bool
    credential_bound: bool | None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def is_restricted_outbound_violation(
    *, data_classification: str, provider_allowlist: list[str]
) -> bool:
    if data_classification != "Restricted":
        return False
    if not provider_allowlist:
        return False
    return any(provider not in LOCAL_PROVIDERS for provider in provider_allowlist)


def serialize_model_route(route: ModelRoute) -> dict[str, Any]:
    return {
        "id": str(route.id),
        "task_type": route.task_type,
        "data_classification": route.data_classification,
        "provider_allowlist": list(route.provider_allowlist),
        "max_cost": float(route.max_cost),
        "fallback": route.fallback,
        "require_prompt_version": route.require_prompt_version,
        "require_structured_output": route.require_structured_output,
        "credential_present": route.credential_ref is not None,
        "version": route.aggregate_version,
        "created_at": _iso(route.created_at),
        "updated_at": _iso(route.updated_at),
    }


def serialize_invocation_log(row: AIInvocationLog) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "created_at": _iso(row.created_at),
        "created_by": str(row.created_by),
        "model": row.model,
        "prompt_version": row.prompt_version,
        "usage": row.usage,
        "cost": float(row.cost),
        "latency_ms": row.latency_ms,
        "data_classification": row.data_classification,
        "result": row.result,
    }
    if row.user_id is not None:
        payload["user_id"] = str(row.user_id)
    if row.skill_version_id is not None:
        payload["skill_version_id"] = str(row.skill_version_id)
    if row.model_route_id is not None:
        payload["model_route_id"] = str(row.model_route_id)
    if row.copilot_session_id is not None:
        payload["copilot_session_id"] = str(row.copilot_session_id)
    return payload


async def _require_owner_admin(session: AsyncSession, ctx: SessionContext) -> None:
    allowed = await identity_query.caller_is_owner_or_admin(
        session, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if not allowed:
        raise ValueError("forbidden")


def _paginate[T](
    rows: list[T],
    *,
    limit: int | None,
    get_created_at: Callable[[T], datetime],
    get_id: Callable[[T], uuid.UUID],
) -> tuple[list[T], dict[str, Any]]:
    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = repo.encode_created_id_cursor(
            created_at=get_created_at(last), item_id=get_id(last)
        )
    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    if limit is not None:
        page["limit"] = limit
    return rows, page


async def seed_default_model_routes(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
) -> list[ModelRoute]:
    now = datetime.now(UTC)
    routes: list[ModelRoute] = []
    for classification in ("Internal", "Restricted"):
        existing = await repo.get_model_route_by_task(
            session,
            organization_id=organization_id,
            task_type=DEFAULT_TASK_TYPE,
            data_classification=classification,
        )
        if existing is not None:
            routes.append(existing)
            continue
        allowlist = ["local"] if classification == "Restricted" else ["openai"]
        route = await repo.create_model_route(
            session,
            organization_id=organization_id,
            created_at=now,
            created_by=created_by,
            task_type=DEFAULT_TASK_TYPE,
            data_classification=classification,
            provider_allowlist=allowlist,
            max_cost=Decimal("10"),
            fallback={"strategy": "degrade"},
            require_prompt_version=True,
            require_structured_output=False,
            credential_ref=None,
        )
        routes.append(route)
    return routes


async def list_model_routes_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    task_type: str | None,
    data_classification: str | None,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    if limit is not None and limit < 1:
        raise ValueError("validation")
    if data_classification is not None and data_classification not in DATA_CLASSIFICATIONS:
        raise ValueError("validation")

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        try:
            cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
        except ValueError as exc:
            raise ValueError("invalid_cursor") from exc

    rows = await repo.list_model_routes(
        session,
        organization_id=ctx.organization.id,
        task_type=task_type,
        data_classification=data_classification,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=limit,
    )
    visible, page = _paginate(
        rows,
        limit=limit,
        get_created_at=lambda item: item.created_at,
        get_id=lambda item: item.id,
    )
    return {
        "items": [serialize_model_route(item) for item in visible],
        "page": page,
    }


async def put_model_route_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    model_route_id: uuid.UUID,
    body: ModelRoutePutInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    org_id = ctx.organization.id

    if body.data_classification not in DATA_CLASSIFICATIONS:
        raise ValueError("validation")
    if is_restricted_outbound_violation(
        data_classification=body.data_classification,
        provider_allowlist=body.provider_allowlist,
    ):
        raise ValueError("policy_deny")

    existing_idem = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_MODEL_ROUTE_PUT,
        idempotency_key=idempotency_key,
    )
    if existing_idem is not None:
        if existing_idem.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing_idem.response_ref or {})

    route = await repo.get_model_route(
        session, organization_id=org_id, model_route_id=model_route_id
    )
    if route is None:
        raise ValueError("not_found")
    if route.aggregate_version != body.expected_version:
        raise ValueError("version")

    now = datetime.now(UTC)
    route.task_type = body.task_type
    route.data_classification = body.data_classification
    route.provider_allowlist = list(body.provider_allowlist)
    route.max_cost = body.max_cost
    route.fallback = body.fallback
    route.require_prompt_version = body.require_prompt_version
    route.require_structured_output = body.require_structured_output
    if body.credential_bound is False:
        route.credential_ref = None
    # True keeps an existing ref; M0 cannot bind a real credential_ref (no Vault).
    route.updated_at = now
    route.aggregate_version += 1
    await session.flush()

    payload = serialize_model_route(route)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="model_route.put",
            resource_type="model_route",
            resource_id=route.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_MODEL_ROUTE_PUT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    return payload


async def connection_test_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    model_route_id: uuid.UUID,
    expected_version: int,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    org_id = ctx.organization.id

    existing_idem = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTION_TEST,
        idempotency_key=idempotency_key,
    )
    if existing_idem is not None:
        if existing_idem.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing_idem.response_ref or {})

    route = await repo.get_model_route(
        session, organization_id=org_id, model_route_id=model_route_id
    )
    if route is None:
        raise ValueError("not_found")
    if route.aggregate_version != expected_version:
        raise ValueError("version")

    started = time.perf_counter()
    reachable = False
    error_class: str | None = None

    if route.data_classification == "Restricted":
        reachable = True
    elif route.credential_ref is None:
        reachable = False
        error_class = "credential_missing"
    else:
        reachable = True

    latency_ms = max(1, int((time.perf_counter() - started) * 1000))
    payload: dict[str, Any] = {"reachable": reachable, "latency_ms": latency_ms}
    if error_class is not None:
        payload["error_class"] = error_class

    now = datetime.now(UTC)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="model_route.connection_test",
            resource_type="model_route",
            resource_id=route.id,
            result="ok" if reachable else "failed",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTION_TEST,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=payload,
        created_by=ctx.user.id,
        created_at=now,
    )
    return payload


async def list_invocation_logs_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    user_id: uuid.UUID | None,
    result: str | None,
    model: str | None,
    copilot_session_id: uuid.UUID | None,
    created_from: datetime | None,
    created_to: datetime | None,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    if limit is not None and limit < 1:
        raise ValueError("validation")
    if result is not None and result not in INVOCATION_RESULTS:
        raise ValueError("validation")

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        try:
            cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)
        except ValueError as exc:
            raise ValueError("invalid_cursor") from exc

    rows = await repo.list_invocation_logs(
        session,
        organization_id=ctx.organization.id,
        user_id=user_id,
        result_filter=result,
        model=model,
        copilot_session_id=copilot_session_id,
        created_from=created_from,
        created_to=created_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=limit,
    )
    visible, page = _paginate(
        rows,
        limit=limit,
        get_created_at=lambda item: item.created_at,
        get_id=lambda item: item.id,
    )
    return {
        "items": [serialize_invocation_log(item) for item in visible],
        "page": page,
    }


async def get_invocation_log_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    log_id: uuid.UUID,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    row = await repo.get_invocation_log(session, organization_id=ctx.organization.id, log_id=log_id)
    if row is None:
        raise ValueError("not_found")
    return serialize_invocation_log(row)


def _usage_totals(rows: list[Any]) -> dict[str, int]:
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    for row in rows:
        usage = row.usage if isinstance(row.usage, dict) else {}
        prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        total_tokens += int(usage.get("total_tokens", 0) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


async def get_cost_dashboard_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    created_from: datetime,
    created_to: datetime,
    project_id: uuid.UUID | None,
) -> dict[str, Any]:
    await _require_owner_admin(session, ctx)
    if created_from > created_to:
        raise ValueError("validation")
    _ = project_id

    rows = await repo.list_invocation_logs_in_window(
        session,
        organization_id=ctx.organization.id,
        created_from=created_from,
        created_to=created_to,
    )
    total = len(rows)
    ok_count = sum(1 for row in rows if row.result == "ok")
    degraded_count = sum(1 for row in rows if row.result == "degraded")
    cost_total = float(sum((row.cost for row in rows), Decimal("0")))

    adoption_rate = ok_count / total if total > 0 else 0.0
    degrade_rate = degraded_count / total if total > 0 else 0.0

    return {
        "window": {"from": _iso(created_from), "to": _iso(created_to)},
        "totals": {
            "token_usage": _usage_totals(rows),
            "cost": cost_total,
            "invocation_count": total,
            "adoption_rate": adoption_rate,
            "degrade_rate": degrade_rate,
            "cost_per_workflow": {},
        },
        "series": [],
    }
