import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionOrToken
from app.modules.execution_registry import query_port as execution_query
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.models import TestRun
from app.modules.test_assets import query_port as test_assets_query

COMMAND_TYPE_START = "test_run.start_session"
COMMAND_TYPE_CANCEL = "test_run.cancel"
COMMAND_TYPE_TO_SCRIPT_DRAFT = "test_run.to_script_draft"

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


def serialize_start_response(
    run: TestRun, *, receipt_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    payload = serialize_detail(run, now=now)
    payload["receipt"] = {
        "id": str(receipt_id),
        "command_type": COMMAND_TYPE_START,
        "status": "accepted",
        "accepted_at": _iso(now),
        "resource_type": "TestRun",
        "resource_id": str(run.id),
    }
    payload["poll"] = {
        "path": f"/api/v1/command-receipts/{receipt_id}",
        "sse_path": f"/api/v1/test-runs/{run.id}/events",
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


async def list_test_runs_for_auth(
    session: AsyncSession,
    auth: SessionOrToken,
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
    if auth.token is not None:
        if project_id not in list(auth.token.project_ids):
            raise ValueError("token_project")
        org_id = auth.organization_id
    else:
        assert auth.session is not None
        await _require_project_read(session, auth.session, project_id=project_id)
        org_id = auth.session.organization.id

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
        organization_id=org_id,
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
    auth = SessionOrToken(session=ctx, token=None)
    return await list_test_runs_for_auth(
        session,
        auth,
        project_id=project_id,
        status=status,
        execution_source=execution_source,
        trigger_type=trigger_type,
        plan_id=plan_id,
        env_id=env_id,
        include_waiting=include_waiting,
        sort=sort,
        cursor=cursor,
        limit=limit,
    )


async def get_test_run_for_auth(
    session: AsyncSession,
    auth: SessionOrToken,
    *,
    test_run_id: uuid.UUID,
) -> dict[str, Any]:
    run = await repo.get_test_run(
        session,
        organization_id=auth.organization_id,
        test_run_id=test_run_id,
    )
    if run is None:
        raise ValueError("not_found")
    if auth.token is not None:
        allowed = list(auth.token.project_ids)
        if run.project_id not in allowed:
            raise ValueError("not_found")
    else:
        assert auth.session is not None
        role = await identity_query.get_project_membership_role(
            session,
            organization_id=auth.organization_id,
            project_id=run.project_id,
            user_id=auth.session.user.id,
        )
        if role is None or role not in READ_ROLES:
            raise ValueError("not_found")
    return serialize_detail(run)


async def get_test_run_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
) -> dict[str, Any]:
    run = await _get_visible_test_run(session, ctx, test_run_id=test_run_id)
    return serialize_detail(run)


async def start_test_run_api_token(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    token_project_ids: list[uuid.UUID],
    body: dict[str, Any],
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    project_id = uuid.UUID(str(body["project_id"]))
    if project_id not in token_project_ids:
        raise ValueError("token_project")
    if body.get("trigger_type") not in (None, "api_token"):
        raise ValueError("validation")
    body_payload = dict(body)
    body_payload["trigger_type"] = "api_token"
    return await _start_test_run_core(
        session,
        organization_id=organization_id,
        user_id=user_id,
        body=body_payload,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        enforce_execute_role=False,
    )


async def start_test_run_session(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: dict[str, Any],
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], bool]:
    project_id = uuid.UUID(str(body["project_id"]))
    await _require_project_execute(session, ctx, project_id=project_id)
    return await _start_test_run_core(
        session,
        organization_id=ctx.organization.id,
        user_id=ctx.user.id,
        body=body,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        enforce_execute_role=True,
    )


async def _start_test_run_core(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    body: dict[str, Any],
    idempotency_key: str,
    request_hash: str,
    enforce_execute_role: bool,
) -> tuple[dict[str, Any], bool]:
    _ = enforce_execute_role
    org_id = organization_id
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
            return existing.response_ref, False

    project_id = uuid.UUID(str(body["project_id"]))
    env_id = uuid.UUID(str(body["env_id"]))
    execution_source = str(body["execution_source"])
    case_ids_raw = body["case_ids"]
    trigger_type_raw = body.get("trigger_type")
    trigger_type = "manual" if trigger_type_raw is None else str(trigger_type_raw)
    plan_id_raw = body.get("plan_id")
    params = body.get("params")
    expected_env_version = body.get("expected_env_version")

    if execution_source not in VALID_EXECUTION_SOURCES:
        raise ValueError("validation")
    if trigger_type == "api_token":
        valid_triggers = frozenset({"api_token"})
    else:
        valid_triggers = VALID_START_TRIGGER_TYPES
    if trigger_type not in valid_triggers:
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
    cases = await test_assets_query.get_cases_for_run_validation(
        session,
        organization_id=org_id,
        project_id=project_id,
        case_ids=case_ids,
    )
    snapshot["case_version_ids"] = [
        str(case["version_id"]) for case in cases if case.get("version_id") is not None
    ]

    perf_cases = [case for case in cases if case.get("case_type") == "performance"]
    if perf_cases:
        # FR-11: perf runs are script-source, homogeneous, whitelist-gated.
        if len(perf_cases) != len(cases) or execution_source != "script":
            raise ValueError("validation")
        whitelist = (
            params_redacted.get("perf_whitelist") if isinstance(params_redacted, dict) else None
        )
        base_url = (
            str(params_redacted.get("TARGET_ENV", "")) if isinstance(params_redacted, dict) else ""
        )
        if (
            not isinstance(whitelist, list)
            or not whitelist
            or not base_url
            or not any(base_url.startswith(str(prefix)) for prefix in whitelist)
        ):
            # AC-051: whitelist-miss targets are denied outright, no approval.
            raise ValueError("perf_policy")
        if (
            await repo.find_active_perf_run_for_scenario(
                session,
                organization_id=org_id,
                test_case_id=uuid.UUID(str(perf_cases[0]["id"])),
                exclude_run_id=uuid.uuid4(),
            )
            is not None
        ):
            # AC-054: accepted but queued behind the in-flight scenario run.
            snapshot["perf_queued"] = True

    run = await repo.create_test_run(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=plan_id,
        env_id=env_id,
        execution_source=execution_source,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        status="PENDING",
        snapshot=snapshot,
    )

    receipt_id = uuid.uuid4()

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=user_id,
            action="test_run.start_session",
            resource_type="TestRun",
            resource_id=run.id,
            project_id=project_id,
            result="accepted",
            request_hash=request_hash,
        ),
    )

    response = serialize_start_response(run, receipt_id=receipt_id, now=now)
    await repo.create_command_receipt(
        session,
        receipt_id=receipt_id,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        command_type=COMMAND_TYPE_START,
        status="accepted",
        accepted_at=now,
        resource_type="TestRun",
        resource_id=run.id,
        project_id=project_id,
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_START,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=user_id,
        created_at=now,
    )
    return response, True


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
) -> tuple[dict[str, Any], int, uuid.UUID | None]:
    _ = reason
    org_id = ctx.organization.id
    now = datetime.now(UTC)
    ci_collect_run_id: uuid.UUID | None = None

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
            return existing.response_ref["data"], int(status_code), None

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
        if run.status == "WAITING_EXTERNAL" and run.execution_source == "external_ci":
            summary = run.result_summary if isinstance(run.result_summary, dict) else {}
            ci = summary.get("ci")
            if isinstance(ci, dict) and ci.get("trigger_state") == "triggered":
                ci_collect_run_id = run.id
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
    await repo.create_command_receipt(
        session,
        receipt_id=receipt_id,
        organization_id=org_id,
        created_at=now,
        created_by=ctx.user.id,
        command_type=COMMAND_TYPE_CANCEL,
        status="accepted",
        accepted_at=now,
        resource_type="TestRun",
        resource_id=run.id,
        project_id=run.project_id,
    )
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
    return data, http_status, ci_collect_run_id


async def reclaim_stale_active_runs(
    session: AsyncSession,
    *,
    now: datetime,
    heartbeat_timeout_seconds: int,
    organization_id: uuid.UUID | None = None,
) -> int:
    from app.modules.run_orchestration.executor import complete_stopping_runs

    stopped = await complete_stopping_runs(session, organization_id=organization_id, now=now)
    reclaimed = await repo.reclaim_stale_active_runs(
        session,
        organization_id=organization_id,
        now=now,
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )
    return stopped + reclaimed


async def get_execution_options_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    execution_source: str | None,
    plan_id: uuid.UUID | None,
) -> dict[str, Any]:
    _ = plan_id
    await _require_project_read(session, ctx, project_id=project_id)
    if execution_source is not None and execution_source not in VALID_EXECUTION_SOURCES:
        raise ValueError("validation")
    environments = await execution_query.list_environments_for_execution_options(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
    )
    cases = await test_assets_query.list_cases_for_execution_options(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        execution_source=execution_source,
    )
    agent_times_external_ci_allowed = False
    return {
        "project_id": str(project_id),
        "environments": [
            {
                "id": str(item["id"]),
                "name": item["name"],
                "env_type": item["env_type"],
                "status": item["status"],
                "selectable": item["selectable"],
                "unavailable_reason": item["unavailable_reason"],
                "health_status": item["health_status"],
                "capacity": item["capacity"],
                "credential_present": item["credential_present"],
                "version": item["version"],
            }
            for item in environments
        ],
        "cases": [
            {
                "id": str(item["id"]),
                "title": item["title"],
                "lifecycle_status": item["lifecycle_status"],
                "validity": item["validity"],
                "execution_mode": item["execution_mode"],
                "case_type": item.get("case_type"),
                "job_id": item.get("job_id"),
                "selectable": item["selectable"],
                "unavailable_reason": item["unavailable_reason"],
            }
            for item in cases
        ],
        "combo_constraints": {"agent_times_external_ci_allowed": agent_times_external_ci_allowed},
    }


async def get_command_receipt_for_caller(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    receipt_id: uuid.UUID,
) -> dict[str, Any]:
    receipt = await repo.get_command_receipt(
        session,
        organization_id=organization_id,
        receipt_id=receipt_id,
    )
    if receipt is None:
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=organization_id,
        project_id=receipt.project_id,
        user_id=user_id,
    )
    if role is None:
        raise ValueError("not_found")
    if receipt.created_by != user_id and role not in {"owner", "admin"}:
        raise ValueError("not_found")
    return {
        "id": str(receipt.id),
        "command_type": receipt.command_type,
        "status": receipt.status,
        "accepted_at": _iso(receipt.accepted_at),
        "resource_type": receipt.resource_type,
        "resource_id": str(receipt.resource_id),
        "poll": {
            "path": f"/api/v1/command-receipts/{receipt.id}",
            "sse_path": (
                f"/api/v1/test-runs/{receipt.resource_id}/events"
                if receipt.resource_type == "TestRun"
                else f"/api/v1/command-receipts/{receipt.id}/events"
            ),
        },
    }


async def create_script_draft_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_run_id: uuid.UUID,
    expected_run_version: int | None,
    title: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    """API-068: agent trajectory → new TestCase DRAFT (sync; run untouched)."""
    from app.modules.results_evidence import query_port as evidence_query
    from app.modules.test_assets import command_port as test_assets_command

    org_id = ctx.organization.id
    run = await _get_visible_test_run(session, ctx, test_run_id=test_run_id, for_update=True)
    await _require_project_execute(session, ctx, project_id=run.project_id)
    if expected_run_version is not None and run.aggregate_version != expected_run_version:
        raise ValueError("version")

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_TO_SCRIPT_DRAFT,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        stored = existing.response_ref
        if isinstance(stored, dict):
            return dict(stored.get("data") or {})
        return {}

    if run.execution_source != "agent":
        raise ValueError("state")
    trajectory = await evidence_query.get_agent_trajectory_record(
        session,
        organization_id=org_id,
        test_run_id=test_run_id,
    )
    if trajectory is None or trajectory.get("status") != "completed":
        raise ValueError("state")

    executed_raw = trajectory.get("executed_steps")
    if not isinstance(executed_raw, list) or not executed_raw:
        raise ValueError("schema")
    draft_steps: list[dict[str, Any]] = []
    for item in executed_raw:
        if not isinstance(item, dict) or not isinstance(item.get("action"), dict):
            raise ValueError("schema")
        action = item["action"]
        if str(item.get("tool", "")) != "request" or not isinstance(action.get("params"), dict):
            # Only request tools are convertible in the M2 pilot.
            raise ValueError("schema")
        draft_steps.append({"action": "request", "params": dict(action["params"])})

    raw_meta = trajectory.get("meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    assertions_raw = meta.get("assertions")
    draft_assertions = (
        [item for item in assertions_raw if isinstance(item, dict)]
        if isinstance(assertions_raw, list)
        else []
    )

    draft_title = title if title else f"agent-draft-{str(test_run_id)[:8]}"
    test_case = await test_assets_command.create_script_draft_from_trajectory(
        session,
        organization_id=org_id,
        project_id=run.project_id,
        created_by=ctx.user.id,
        title=draft_title,
        steps=draft_steps,
        assertions=draft_assertions,
        source_test_run_id=test_run_id,
    )
    response = {"test_case": test_case, "test_run_id": str(test_run_id)}

    now = datetime.now(UTC)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="agent.to_script_draft",
            resource_type="TestRun",
            resource_id=test_run_id,
            project_id=run.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_TO_SCRIPT_DRAFT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref={"data": response},
        created_by=ctx.user.id,
        created_at=now,
    )
    return response
