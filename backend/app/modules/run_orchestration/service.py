import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import query_port as execution_query
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.models import TestRun

COMMAND_TYPE_START = "test_run.start_session"
COMMAND_TYPE_CANCEL = "test_run.cancel"

EXECUTE_ROLES = frozenset({"owner", "admin", "tester"})
READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})

VALID_STATUSES = frozenset(
    {
        "PENDING",
        "VALIDATING",
        "RUNNING",
        "WAITING_EXTERNAL",
        "WAITING_APPROVAL",
        "STOPPING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "TIMEOUT",
    }
)
VALID_EXECUTION_SOURCES = frozenset({"script", "agent", "external_ci"})
VALID_TRIGGER_TYPES = frozenset({"manual", "schedule", "ci_webhook", "api_token"})
VALID_START_TRIGGER_TYPES = frozenset({"manual", "schedule"})
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"})
WAITING_STATUSES = frozenset({"WAITING_APPROVAL", "WAITING_EXTERNAL"})
SECRET_NESTED_KEYS = frozenset({"password", "secret", "token", "credential_ref"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _dwell_seconds(run: TestRun, *, now: datetime) -> int | None:
    if run.status not in WAITING_STATUSES:
        return None
    updated = run.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return max(0, int((now - updated).total_seconds()))


def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "case_ids": snapshot.get("case_ids", []),
        "env_id": snapshot.get("env_id"),
        "env_config_version": snapshot.get("env_config_version"),
        "params_redacted": snapshot.get("params_redacted", {}),
    }
    case_version_ids = snapshot.get("case_version_ids")
    if case_version_ids is not None:
        summary["case_version_ids"] = case_version_ids
    return summary


def serialize_list_item(run: TestRun, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "id": str(run.id),
        "project_id": str(run.project_id),
        "env_id": str(run.env_id),
        "execution_source": run.execution_source,
        "trigger_type": run.trigger_type,
        "status": run.status,
        "version": run.aggregate_version,
        "gate_evaluation_id": str(run.gate_evaluation_id) if run.gate_evaluation_id else None,
        "created_at": _iso(run.created_at),
        "updated_at": _iso(run.updated_at),
    }
    if run.plan_id is not None:
        payload["plan_id"] = str(run.plan_id)
    dwell = _dwell_seconds(run, now=now)
    if dwell is not None:
        payload["dwell_seconds"] = dwell
    return payload


def serialize_detail(run: TestRun, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    payload = serialize_list_item(run, now=now)
    payload["snapshot_summary"] = _snapshot_summary(run.snapshot)
    payload["last_heartbeat_at"] = _iso(run.last_heartbeat_at) if run.last_heartbeat_at else None
    payload["stop_signal_at"] = _iso(run.stop_signal_at) if run.stop_signal_at else None
    payload["result_summary"] = run.result_summary
    payload["execution_source_badge"] = {
        "skips_quality_gate": run.execution_source == "agent",
        "normalized_from_external_ci": run.execution_source == "external_ci",
    }
    return payload


def serialize_start_response(run: TestRun, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    payload = serialize_detail(run, now=now)
    receipt_id = str(uuid.uuid4())
    payload["receipt"] = {
        "id": receipt_id,
        "command_type": COMMAND_TYPE_START,
        "status": "accepted",
        "accepted_at": _iso(now),
        "resource_type": "TestRun",
        "resource_id": str(run.id),
    }
    return payload


def _reject_nested_secrets(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if key in SECRET_NESTED_KEYS and value is not None and value != "":
            raise ValueError("validation")
        if isinstance(value, dict):
            _reject_nested_secrets(value)


def _redact_params(params: dict[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    redacted: dict[str, Any] = {}
    for key, value in params.items():
        if key in SECRET_NESTED_KEYS:
            redacted[key] = ""
        elif isinstance(value, dict):
            redacted[key] = _redact_params(value)
        else:
            redacted[key] = value
    return redacted


async def _require_project_read(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
) -> str:
    org_id = ctx.organization.id
    if not await identity_query.project_exists_in_org(
        session, organization_id=org_id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return role


async def _require_project_execute(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
) -> None:
    org_id = ctx.organization.id
    if not await identity_query.project_exists_in_org(
        session, organization_id=org_id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None:
        raise ValueError("not_found")
    if role not in EXECUTE_ROLES:
        raise ValueError("forbidden")


async def _get_visible_test_run(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
    for_update: bool = False,
) -> TestRun:
    run = await repo.get_test_run(
        session,
        organization_id=ctx.organization.id,
        test_run_id=test_run_id,
        for_update=for_update,
    )
    if run is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=run.project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in READ_ROLES:
        raise ValueError("not_found")
    return run


async def list_test_runs_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID | None,
    status: str | None,
    execution_source: str | None,
    trigger_type: str | None,
    plan_id: uuid.UUID | None,
    env_id: uuid.UUID | None,
    include_waiting: bool,
    sort: str | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    if project_id is None:
        raise ValueError("validation")
    await _require_project_read(session, ctx, project_id=project_id)

    if status is not None and status not in VALID_STATUSES:
        raise ValueError("validation")
    if execution_source is not None and execution_source not in VALID_EXECUTION_SOURCES:
        raise ValueError("validation")
    if trigger_type is not None and trigger_type not in VALID_TRIGGER_TYPES:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")

    sort_desc = True
    if sort is not None:
        if sort == "-created_at":
            sort_desc = True
        elif sort == "created_at":
            sort_desc = False
        else:
            raise ValueError("validation")

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    fetch_limit = None if limit is None else limit + 1
    now = datetime.now(UTC)
    rows = await repo.list_test_runs(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        status=status,
        execution_source=execution_source,
        trigger_type=trigger_type,
        plan_id=plan_id,
        env_id=env_id,
        include_waiting=include_waiting,
        sort_desc=sort_desc,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=fetch_limit,
    )

    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]

    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = repo.encode_created_id_cursor(created_at=last.created_at, item_id=last.id)

    return {
        "items": [serialize_list_item(row, now=now) for row in rows],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_test_run_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
) -> dict[str, Any]:
    run = await _get_visible_test_run(session, ctx, test_run_id=test_run_id)
    return serialize_detail(run)


async def start_test_run_session(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_START,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    project_id = uuid.UUID(str(body["project_id"]))
    env_id = uuid.UUID(str(body["env_id"]))
    execution_source = str(body["execution_source"])
    case_ids_raw = body["case_ids"]
    trigger_type = str(body.get("trigger_type", "manual"))
    plan_id_raw = body.get("plan_id")
    params = body.get("params")
    expected_env_version = body.get("expected_env_version")

    await _require_project_execute(session, ctx, project_id=project_id)

    if execution_source not in VALID_EXECUTION_SOURCES:
        raise ValueError("validation")
    if trigger_type not in VALID_START_TRIGGER_TYPES:
        raise ValueError("validation")
    if not isinstance(case_ids_raw, list) or len(case_ids_raw) == 0:
        raise ValueError("validation")
    try:
        case_ids = [uuid.UUID(str(cid)) for cid in case_ids_raw]
    except (TypeError, ValueError) as exc:
        raise ValueError("validation") from exc

    if params is not None:
        if not isinstance(params, dict):
            raise ValueError("validation")
        _reject_nested_secrets(params)
    params_redacted = _redact_params(params if isinstance(params, dict) else None)

    plan_id: uuid.UUID | None = None
    if plan_id_raw is not None:
        plan_id = uuid.UUID(str(plan_id_raw))

    env_info = await execution_query.get_environment_for_start(
        session, organization_id=org_id, environment_id=env_id
    )
    if env_info is None:
        raise ValueError("not_found")
    if env_info["scope_level"] == "project" and env_info["project_id"] != project_id:
        raise ValueError("not_found")
    if env_info["status"] != "ACTIVE":
        raise ValueError("state")
    if expected_env_version is not None and env_info["version"] != expected_env_version:
        raise ValueError("version")
    if execution_source == "agent" and env_info["env_type"] == "external_ci":
        raise ValueError("validation")

    snapshot: dict[str, Any] = {
        "case_ids": [str(cid) for cid in case_ids],
        "env_id": str(env_id),
        "env_config_version": env_info["config_version"],
        "execution_source": execution_source,
        "trigger_type": trigger_type,
        "params_redacted": params_redacted,
    }
    if execution_source == "agent":
        snapshot["skips_quality_gate"] = True

    run = await repo.create_test_run(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=ctx.user.id,
        project_id=project_id,
        plan_id=plan_id,
        env_id=env_id,
        execution_source=execution_source,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        status="PENDING",
        snapshot=snapshot,
    )

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="test_run.start_session",
            resource_type="TestRun",
            resource_id=run.id,
            project_id=project_id,
            result="accepted",
            request_hash=request_hash,
        ),
    )

    response = serialize_start_response(run, now=now)
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_START,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


def _build_cancel_receipt(
    *,
    receipt_id: uuid.UUID,
    run: TestRun,
    accepted_at: datetime,
) -> dict[str, Any]:
    return {
        "id": str(receipt_id),
        "command_type": COMMAND_TYPE_CANCEL,
        "status": "accepted",
        "accepted_at": _iso(accepted_at),
        "resource_type": "TestRun",
        "resource_id": str(run.id),
    }


async def cancel_test_run(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
    expected_version: int,
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], int]:
    _ = reason
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CANCEL,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            status_code = existing.response_ref.get("_http_status", 200)
            return existing.response_ref["data"], int(status_code)

    run = await _get_visible_test_run(session, ctx, test_run_id=test_run_id, for_update=True)
    await _require_project_execute(session, ctx, project_id=run.project_id)

    if run.aggregate_version != expected_version:
        raise ValueError("version")

    http_status = 200
    receipt_id = uuid.uuid4()

    if run.status == "STOPPING":
        raise ValueError("state")

    if run.status in TERMINAL_STATUSES:
        raise ValueError("state")

    if run.status == "VALIDATING":
        raise ValueError("state")

    if run.status in {"PENDING", "WAITING_APPROVAL", "WAITING_EXTERNAL"}:
        run = await repo.update_test_run_cancel(
            session,
            run=run,
            new_status="CANCELLED",
            updated_at=now,
            stop_signal_at=now,
        )
        http_status = 200
    elif run.status == "RUNNING":
        run = await repo.update_test_run_cancel(
            session,
            run=run,
            new_status="STOPPING",
            updated_at=now,
            stop_signal_at=now,
        )
        http_status = 202
    else:
        raise ValueError("state")

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="test_run.cancel",
            resource_type="TestRun",
            resource_id=run.id,
            project_id=run.project_id,
            result="accepted",
            request_hash=request_hash,
        ),
    )

    receipt = _build_cancel_receipt(receipt_id=receipt_id, run=run, accepted_at=now)
    data = {
        "receipt": receipt,
        "test_run": serialize_detail(run, now=now),
    }
    stored = {"data": data, "_http_status": http_status}
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CANCEL,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=stored,
        created_by=ctx.user.id,
        created_at=now,
    )
    return data, http_status


async def reclaim_stale_active_runs(
    session: AsyncSession,
    *,
    now: datetime,
    heartbeat_timeout_seconds: int,
    organization_id: uuid.UUID | None = None,
) -> int:
    return await repo.reclaim_stale_active_runs(
        session,
        organization_id=organization_id,
        now=now,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )
