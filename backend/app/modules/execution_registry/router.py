import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    idempotency_conflict,
    not_found,
    policy_deny,
    policy_undeclared,
    precondition_failed,
    require_reauth,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.execution_registry import repository as repo
from app.modules.execution_registry.service import (
    disable_execution_environment,
    get_environment_for_caller,
    get_health_projection_for_caller,
    get_params_schema_for_caller,
    list_environments_for_caller,
    list_jobs_for_caller,
    register_execution_environment,
)
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key

router = APIRouter(prefix="/api/v1")


def _parse_body[TModel: BaseModel](model: type[TModel], raw: bytes, trace_id: str) -> TModel:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


EnvTypeLiteral = Literal["platform_executor", "external_ci"]
ScopeLevelLiteral = Literal["organization", "project"]
StatusLiteral = Literal["PENDING_APPROVAL", "ACTIVE", "DEGRADED", "DISABLED"]


class JobContractInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    supports_cancel: bool = False
    contract_version: int = Field(default=1, ge=1)
    params_schema_ref: str | None = None
    params_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    report_adapter: str | None = None
    artifact_manifest: dict[str, Any] | None = None


class ExecutionEnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env_type: EnvTypeLiteral
    name: str
    scope_level: ScopeLevelLiteral
    project_id: uuid.UUID
    endpoint: str | None = None
    credential_ref: str | None = None
    credential_ref_present: bool | None = None
    job_contracts: list[JobContractInput] | None = None
    preview_id: uuid.UUID | None = None


class ExecutionEnvironmentDisable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = None


class CredentialRefBind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_ref: str
    expected_version: int | None = Field(default=None, ge=1)


def _map_read_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code in {"validation", "invalid_cursor"}:
        raise validation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _map_write_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "policy_deny":
        raise policy_deny(trace_id) from exc
    if code == "policy_undeclared":
        raise policy_undeclared(trace_id) from exc
    if code == "require_reauth":
        raise require_reauth(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/execution-environments")
async def api_100_list_execution_environments(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    env_type: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_environments_for_caller(
            db,
            ctx,
            project_id=project_id,
            env_type=env_type,
            status=status,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/execution-environments/{environment_id}")
async def api_101_get_execution_environment(
    request: Request,
    environment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_environment_for_caller(db, ctx, environment_id=environment_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.post("/execution-environments")
async def api_102_register_execution_environment(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ExecutionEnvironmentCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await register_execution_environment(
            db,
            ctx,
            settings,
            body=body.model_dump(mode="json", by_alias=True),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/execution-environments/{environment_id}/disable")
async def api_103_disable_execution_environment(
    request: Request,
    environment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ExecutionEnvironmentDisable, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await disable_execution_environment(
            db,
            ctx,
            environment_id=environment_id,
            expected_version=body.expected_version,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/execution-environments/{environment_id}/jobs")
async def api_104_list_jobs(
    request: Request,
    environment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    q: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_jobs_for_caller(
            db,
            ctx,
            environment_id=environment_id,
            q=q,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/execution-environments/{environment_id}/health")
async def api_105_get_health(
    request: Request,
    environment_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_health_projection_for_caller(db, ctx, environment_id=environment_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/execution-environments/{environment_id}/jobs/{job_id}/params-schema")
async def api_070_get_params_schema(
    request: Request,
    environment_id: uuid.UUID,
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_params_schema_for_caller(
            db,
            ctx,
            environment_id=environment_id,
            job_id=job_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.post("/connectors/{connector_id}/credential-refs")
async def api_106_bind_credential_ref(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    _ = connector_id
    _ = db
    _ = ctx
    trace_id = get_trace_id(request)
    raw = await request.body()
    if raw:
        try:
            CredentialRefBind.model_validate_json(raw)
        except ValidationError as exc:
            raise validation_failed(trace_id) from exc
    raise not_found(trace_id)
