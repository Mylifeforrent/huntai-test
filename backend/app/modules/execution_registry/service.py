import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.approval_policy import command_port as approval_command
from app.modules.approval_policy import query_port as approval_query
from app.modules.approval_policy.policy_gate import PolicyGate, evaluate_policy_gate
from app.modules.execution_registry import repository as repo
from app.modules.execution_registry.models import ExecutionEnvironment, JobContract
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext, compute_reauth_required
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration.report_adapters import SUPPORTED_REPORT_ADAPTERS

COMMAND_TYPE_REGISTER = "execution_environment.register"
COMMAND_TYPE_DISABLE = "execution_environment.disable"

VALID_ENV_TYPES = frozenset({"platform_executor", "external_ci"})
VALID_SCOPE_LEVELS = frozenset({"organization", "project"})
VALID_STATUSES = frozenset({"PENDING_APPROVAL", "ACTIVE", "DEGRADED", "DISABLED"})
FORBIDDEN_REGISTER_KEYS = frozenset(
    {
        "status",
        "standing_auth_metadata",
        "standing_auth",
        "gate",
        "has_credential",
        "credential_present",
    }
)
SECRET_NESTED_KEYS = frozenset({"password", "secret", "token", "credential_ref"})


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _credential_present(env: ExecutionEnvironment) -> bool:
    return bool(env.credential_ref and env.credential_ref.strip())


def serialize_list_item(env: ExecutionEnvironment) -> dict[str, Any]:
    return {
        "id": str(env.id),
        "env_type": env.env_type,
        "name": env.name,
        "endpoint": env.endpoint,
        "status": env.status,
        "scope_level": env.scope_level,
        "credential_present": _credential_present(env),
        "version": env.aggregate_version,
        "created_at": _iso(env.created_at),
        "updated_at": _iso(env.updated_at),
    }


def serialize_detail(env: ExecutionEnvironment) -> dict[str, Any]:
    payload = serialize_list_item(env)
    payload["health_status"] = env.health_status
    payload["capacity"] = env.capacity
    payload["config_version"] = env.config_version
    return payload


def serialize_register_response(
    env: ExecutionEnvironment, *, approval_request_id: uuid.UUID | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(env.id),
        "env_type": env.env_type,
        "name": env.name,
        "status": env.status,
        "version": env.aggregate_version,
        "has_credential": _credential_present(env),
        "endpoint": env.endpoint,
        "health_status": env.health_status,
        "scope_level": env.scope_level,
        "credential_present": _credential_present(env),
        "config_version": env.config_version,
        "created_at": _iso(env.created_at),
        "updated_at": _iso(env.updated_at),
    }
    if approval_request_id is not None:
        payload["approval_request_id"] = str(approval_request_id)
    return payload


def serialize_job_contract(contract: JobContract) -> dict[str, Any]:
    return {
        "job_id": contract.job_id,
        "params_schema_ref": contract.params_schema_ref,
        "report_adapter": contract.report_adapter,
        "supports_cancel": contract.supports_cancel,
        "contract_version": contract.contract_version,
        "artifact_manifest": contract.artifact_manifest,
    }


def serialize_health_projection(env: ExecutionEnvironment) -> dict[str, Any]:
    return {
        "environment_id": str(env.id),
        "status": env.status,
        "health_status": env.health_status,
        "environment_version": env.aggregate_version,
    }


def serialize_params_schema(env_id: uuid.UUID, contract: JobContract) -> dict[str, Any]:
    schema = contract.params_schema if contract.params_schema is not None else {}
    return {
        "environment_id": str(env_id),
        "job_id": contract.job_id,
        "contract_version": contract.contract_version,
        "params_schema_ref": contract.params_schema_ref,
        "schema": schema,
        "supports_cancel": contract.supports_cancel,
    }


async def _user_can_view_environment(
    session: AsyncSession,
    ctx: SessionContext,
    env: ExecutionEnvironment,
) -> bool:
    org_id = ctx.organization.id
    user_id = ctx.user.id
    if env.scope_level == "organization":
        memberships = await identity_query.list_user_project_memberships(
            session, organization_id=org_id, user_id=user_id
        )
        return len(memberships) > 0
    if env.project_id is None:
        return False
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=env.project_id,
        user_id=user_id,
    )
    return role is not None


async def _get_visible_environment(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
    for_update: bool = False,
) -> ExecutionEnvironment:
    env = await repo.get_environment(
        session,
        organization_id=ctx.organization.id,
        environment_id=environment_id,
        for_update=for_update,
    )
    if env is None:
        raise ValueError("not_found")
    if not await _user_can_view_environment(session, ctx, env):
        raise ValueError("not_found")
    return env


def _reject_nested_secrets(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if key in SECRET_NESTED_KEYS and isinstance(value, str) and value.strip():
            raise ValueError("validation")
        if isinstance(value, dict):
            _reject_nested_secrets(value)


def _build_gate_payload(
    *,
    env_type: str,
    name: str,
    scope_level: str,
    endpoint: str | None,
    job_contracts: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "env_type": env_type,
        "name": name,
        "scope_level": scope_level,
    }
    if endpoint is not None:
        payload["endpoint"] = endpoint
    if job_contracts:
        payload["job_contracts"] = job_contracts
    return payload


async def list_environments_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID | None,
    env_type: str | None,
    status: str | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    user_id = ctx.user.id

    if env_type is not None and env_type not in VALID_ENV_TYPES:
        raise ValueError("validation")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")

    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=org_id, user_id=user_id
    )
    if not memberships:
        return {"items": [], "page": {"next_cursor": None}}

    bound_project_id: uuid.UUID | None = None
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
        bound_project_id = project_id

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    user_project_ids = [pid for pid, _ in memberships]
    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_environments(
        session,
        organization_id=org_id,
        project_id=project_id,
        env_type=env_type,
        status=status,
        visible_project_ids=user_project_ids,
        bound_project_id=bound_project_id,
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
        "items": [serialize_list_item(item) for item in rows],
        "page": {"next_cursor": next_cursor},
    }


async def get_environment_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
) -> dict[str, Any]:
    env = await _get_visible_environment(session, ctx, environment_id=environment_id)
    return serialize_detail(env)


async def list_jobs_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
    q: str | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    await _get_visible_environment(session, ctx, environment_id=environment_id)
    if limit is not None and limit < 1:
        raise ValueError("validation")

    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_job_contracts(
        session,
        organization_id=ctx.organization.id,
        execution_environment_id=environment_id,
        job_id_q=q,
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
        "items": [serialize_job_contract(item) for item in rows],
        "page": {"next_cursor": next_cursor},
    }


async def get_health_projection_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
) -> dict[str, Any]:
    env = await _get_visible_environment(session, ctx, environment_id=environment_id)
    return serialize_health_projection(env)


async def get_params_schema_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
    job_id: str,
) -> dict[str, Any]:
    await _get_visible_environment(session, ctx, environment_id=environment_id)
    contract = await repo.get_job_contract(
        session,
        organization_id=ctx.organization.id,
        execution_environment_id=environment_id,
        job_id=job_id,
    )
    if contract is None:
        raise ValueError("not_found")
    return serialize_params_schema(environment_id, contract)


def _normalize_job_contract(item: dict[str, Any]) -> dict[str, Any]:
    """Validate one job contract and return the fields used for persistence."""
    job_id = item.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("validation")
    supports_cancel = item.get("supports_cancel", False)
    contract_version = item.get("contract_version", 1)
    if not isinstance(contract_version, int) or contract_version < 1:
        raise ValueError("validation")
    schema = item.get("schema")
    if schema is not None and not isinstance(schema, dict):
        raise ValueError("validation")
    report_adapter_raw = item.get("report_adapter")
    if report_adapter_raw is not None and (
        not isinstance(report_adapter_raw, str)
        or report_adapter_raw.strip() not in SUPPORTED_REPORT_ADAPTERS
    ):
        raise ValueError("validation")
    params_schema_ref = item.get("params_schema_ref")
    artifact_manifest = item.get("artifact_manifest")
    return {
        "job_id": job_id.strip(),
        "supports_cancel": bool(supports_cancel),
        "contract_version": contract_version,
        "params_schema_ref": params_schema_ref if isinstance(params_schema_ref, str) else None,
        "params_schema": schema if isinstance(schema, dict) else None,
        "artifact_manifest": artifact_manifest if isinstance(artifact_manifest, dict) else None,
        "report_adapter": report_adapter_raw.strip()
        if isinstance(report_adapter_raw, str)
        else None,
    }


async def register_execution_environment(
    session: AsyncSession,
    ctx: SessionContext,
    settings: Settings,
    *,
    body: dict[str, Any],
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    user_id = ctx.user.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_REGISTER,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    for key in FORBIDDEN_REGISTER_KEYS:
        if key in body:
            raise ValueError("policy_deny")

    env_type = body.get("env_type")
    name = body.get("name")
    scope_level = body.get("scope_level")
    project_id_raw = body.get("project_id")
    endpoint = body.get("endpoint")
    credential_ref = body.get("credential_ref")
    credential_ref_present = body.get("credential_ref_present")
    preview_id_raw = body.get("preview_id")
    job_contracts_raw = body.get("job_contracts")

    if (
        not isinstance(env_type, str)
        or env_type not in VALID_ENV_TYPES
        or not isinstance(name, str)
        or not name.strip()
        or not isinstance(scope_level, str)
        or scope_level not in VALID_SCOPE_LEVELS
    ):
        raise ValueError("validation")

    if project_id_raw is None:
        raise ValueError("validation")
    try:
        approval_project_id = uuid.UUID(str(project_id_raw))
    except ValueError as exc:
        raise ValueError("validation") from exc

    persist_project_id = approval_project_id if scope_level == "project" else None

    if not await identity_query.project_exists_in_org(
        session, organization_id=org_id, project_id=approval_project_id
    ):
        raise ValueError("not_found")

    role = await identity_query.get_project_membership_role(
        session,
        organization_id=org_id,
        project_id=approval_project_id,
        user_id=user_id,
    )
    if role not in ("owner", "admin"):
        raise ValueError("forbidden")

    stored_credential_ref: str | None = None
    if isinstance(credential_ref, str) and credential_ref.strip():
        stored_credential_ref = credential_ref.strip()
    elif credential_ref_present is True:
        stored_credential_ref = None

    job_contracts: list[dict[str, Any]] = []
    normalized_contracts: list[dict[str, Any]] = []
    if job_contracts_raw is not None:
        if not isinstance(job_contracts_raw, list):
            raise ValueError("validation")
        for item in job_contracts_raw:
            if not isinstance(item, dict):
                raise ValueError("validation")
            _reject_nested_secrets(item)
            normalized_contracts.append(_normalize_job_contract(item))
            job_contracts.append(item)

    gate_payload = _build_gate_payload(
        env_type=env_type,
        name=name.strip(),
        scope_level=scope_level,
        endpoint=endpoint if isinstance(endpoint, str) else None,
        job_contracts=job_contracts or None,
    )
    _reject_nested_secrets(gate_payload)

    if preview_id_raw is not None:
        try:
            preview_id = uuid.UUID(str(preview_id_raw))
        except ValueError as exc:
            raise ValueError("validation") from exc
        preview = await approval_query.get_action_preview_meta(
            session,
            organization_id=org_id,
            preview_id=preview_id,
        )
        if preview is None:
            raise ValueError("policy_deny")
        preview_action, preview_expires_at = preview
        if preview_action != "env_register":
            raise ValueError("policy_deny")
        if preview_expires_at <= now:
            raise ValueError("policy_deny")

    reauth_required = compute_reauth_required(
        ctx.session, reauth_window_seconds=settings.reauth_window_seconds, now=now
    )
    gate_result = evaluate_policy_gate(
        action_type="env_register",
        payload=gate_payload,
        reauth_required=reauth_required,
    )

    if gate_result.gate == PolicyGate.DENY:
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=org_id,
                actor_user_id=user_id,
                action="execution_environment.register",
                resource_type="execution_environment",
                resource_id=uuid.UUID(int=0),
                project_id=approval_project_id,
                request_hash=request_hash,
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
                organization_id=org_id,
                actor_user_id=user_id,
                action="execution_environment.register",
                resource_type="execution_environment",
                resource_id=uuid.UUID(int=0),
                project_id=approval_project_id,
                request_hash=request_hash,
                result="failed",
            ),
        )
        raise ValueError("require_reauth")

    if gate_result.gate != PolicyGate.REQUIRE_APPROVAL:
        raise ValueError("policy_deny")

    await approval_command.require_env_register_approver(
        session,
        organization_id=org_id,
        project_id=approval_project_id,
        initiator_id=user_id,
    )

    env = await repo.create_environment(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        env_type=env_type,
        name=name.strip(),
        endpoint=endpoint if isinstance(endpoint, str) else None,
        credential_ref=stored_credential_ref,
        scope_level=scope_level,
        project_id=persist_project_id,
    )

    for contract in normalized_contracts:
        await repo.create_job_contract(
            session,
            organization_id=org_id,
            created_at=now,
            created_by=user_id,
            execution_environment_id=env.id,
            job_id=contract["job_id"],
            params_schema_ref=contract["params_schema_ref"],
            params_schema=contract["params_schema"],
            artifact_manifest=contract["artifact_manifest"],
            report_adapter=contract["report_adapter"],
            supports_cancel=contract["supports_cancel"],
            contract_version=contract["contract_version"],
        )

    approval_request_id = await approval_command.create_env_register_approval(
        session,
        settings,
        organization_id=org_id,
        created_by=user_id,
        project_id=approval_project_id,
        target_environment_id=env.id,
        gate_payload=gate_payload,
        initiator_id=user_id,
    )

    response = serialize_register_response(env, approval_request_id=approval_request_id)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=user_id,
            action="execution_environment.register",
            resource_type="execution_environment",
            resource_id=env.id,
            project_id=approval_project_id,
            request_hash=request_hash,
            result="ok",
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_REGISTER,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=user_id,
        created_at=now,
    )
    return response


async def disable_execution_environment(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    environment_id: uuid.UUID,
    expected_version: int,
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    user_id = ctx.user.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_DISABLE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    if expected_version < 1:
        raise ValueError("validation")

    role_on_any = await identity_query.caller_is_owner_or_admin(
        session, organization_id=org_id, user_id=user_id
    )
    if not role_on_any:
        raise ValueError("forbidden")

    env = await _get_visible_environment(
        session, ctx, environment_id=environment_id, for_update=True
    )

    if env.scope_level == "project" and env.project_id is not None:
        role = await identity_query.get_project_membership_role(
            session,
            organization_id=org_id,
            project_id=env.project_id,
            user_id=user_id,
        )
        if role not in ("owner", "admin"):
            raise ValueError("forbidden")

    if env.aggregate_version != expected_version:
        raise ValueError("version")

    if env.status not in ("ACTIVE", "DEGRADED"):
        raise ValueError("state")

    env.status = "DISABLED"
    env.updated_at = now
    env.aggregate_version += 1
    await session.flush()

    response = serialize_register_response(env, approval_request_id=None)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=user_id,
            action="execution_environment.disable",
            resource_type="execution_environment",
            resource_id=env.id,
            project_id=env.project_id,
            request_hash=request_hash,
            result="ok",
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_DISABLE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=user_id,
        created_at=now,
    )
    return response
