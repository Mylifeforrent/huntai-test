import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    hmac_failed,
    idempotency_conflict,
    not_found,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.integration_hub import repository as repo
from app.modules.integration_hub.service import (
    bind_credential_ref_for_caller,
    create_connector_for_caller,
    get_connector_for_caller,
    issue_api_token_for_caller,
    list_api_tokens_for_caller,
    list_connectors_for_caller,
    list_webhook_deliveries_for_caller,
    patch_connector_for_caller,
    process_inbound_webhook,
    put_ci_trigger_bindings_for_caller,
    revoke_api_token_for_caller,
)

router = APIRouter(prefix="/api/v1")

ConnectorTypeLiteral = Literal["jira", "github", "ci", "release"]


class CredentialRefBind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_ref: str
    expected_version: int | None = Field(default=None, ge=1)


ApiTokenScopeLiteral = Literal["read", "write", "execute", "delete"]


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scopes: list[ApiTokenScopeLiteral]
    project_ids: list[uuid.UUID]
    expires_at: datetime
    name: str | None = None


class ApiTokenRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = None


class ConnectorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ConnectorTypeLiteral
    name: str
    auth_method: str
    action_contract: dict[str, Any]
    has_credential_binding: bool | None = None


class ConnectorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = None
    action_contract: dict[str, Any] | None = None
    outbound_write_enabled: bool | None = None


class CiTriggerBindingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str
    ref_pattern: str
    test_plan_id: uuid.UUID
    connector_id: uuid.UUID | None = None


class CiTriggerBindingsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    bindings: list[CiTriggerBindingItem]


def _parse_body[TModel: BaseModel](model: type[TModel], raw: bytes, trace_id: str) -> TModel:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


def _map_read_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "forbidden":
        raise forbidden(trace_id) from exc
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
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    if code == "policy_deny":
        from app.core.errors import policy_deny

        raise policy_deny(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/connectors")
async def api_160_list_connectors(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    type: Annotated[ConnectorTypeLiteral | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_connectors_for_caller(
            db,
            ctx,
            connector_type=type,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/connectors/{connector_id}")
async def api_161_get_connector(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_connector_for_caller(db, ctx, connector_id=connector_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/connectors/{connector_id}/webhook-deliveries")
async def api_164_list_webhook_deliveries(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    signature_ok: Annotated[bool | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_webhook_deliveries_for_caller(
            db,
            ctx,
            connector_id=connector_id,
            signature_ok=signature_ok,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.post("/connectors/{connector_id}/credential-refs")
async def api_106_bind_credential_ref(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(CredentialRefBind, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await bind_credential_ref_for_caller(
            db,
            ctx,
            connector_id=connector_id,
            credential_ref=body.credential_ref,
            expected_version=body.expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/api-tokens")
async def api_170_list_api_tokens(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    issued_to_user_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_api_tokens_for_caller(
            db,
            ctx,
            cursor=cursor,
            limit=limit,
            issued_to_user_id=issued_to_user_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.post("/api-tokens")
async def api_171_issue_api_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ApiTokenCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await issue_api_token_for_caller(
            db,
            ctx,
            scopes=list(body.scopes),
            project_ids=body.project_ids,
            expires_at=body.expires_at,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/api-tokens/{api_token_id}/revocations")
async def api_172_revoke_api_token(
    request: Request,
    api_token_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    _parse_body(ApiTokenRevoke, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await revoke_api_token_for_caller(
            db,
            ctx,
            api_token_id=api_token_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/connectors", status_code=201)
async def api_162_create_connector(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ConnectorCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await create_connector_for_caller(
            db,
            ctx,
            connector_type=body.type,
            name=body.name,
            auth_method=body.auth_method,
            action_contract=body.action_contract,
            has_credential_binding=body.has_credential_binding,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.patch("/connectors/{connector_id}")
async def api_163_patch_connector(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ConnectorPatch, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await patch_connector_for_caller(
            db,
            ctx,
            connector_id=connector_id,
            expected_version=body.expected_version,
            name=body.name,
            action_contract=body.action_contract,
            outbound_write_enabled=body.outbound_write_enabled,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.put("/projects/{project_id}/ci-trigger-bindings")
async def api_167_put_ci_trigger_bindings(
    request: Request,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(CiTriggerBindingsPut, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    bindings = [
        {
            "repository": item.repository,
            "ref_pattern": item.ref_pattern,
            "test_plan_id": str(item.test_plan_id),
            **({"connector_id": str(item.connector_id)} if item.connector_id else {}),
        }
        for item in body.bindings
    ]
    try:
        payload = await put_ci_trigger_bindings_for_caller(
            db,
            ctx,
            project_id=project_id,
            expected_version=body.expected_version,
            bindings=bindings,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.post("/inbound-webhooks/{connector_id}")
async def api_090_inbound_webhook(
    request: Request,
    connector_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    trace_id = get_trace_id(request)
    body = await request.body()
    signature_header = request.headers.get("x-hub-signature-256")
    delivery_id = request.headers.get("x-github-delivery")
    event_type = request.headers.get("x-github-event")
    request_hash = repo.hash_request_body(body)
    try:
        payload, status_code, resume = await process_inbound_webhook(
            db,
            settings,
            connector_id=connector_id,
            body=body,
            signature_header=signature_header,
            delivery_id=delivery_id,
            event_type=event_type,
            request_hash=request_hash,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "not_found":
            raise not_found(trace_id) from exc
        if code == "hmac_failed":
            await db.commit()
            raise hmac_failed(trace_id) from exc
        raise validation_failed(trace_id) from exc
    await db.commit()
    if resume is not None:
        from app.modules.run_orchestration.command_port import resume_ci_run_after_observation

        organization_id, run_id = resume
        background_tasks.add_task(
            resume_ci_run_after_observation,
            organization_id=organization_id,
            test_run_id=run_id,
        )
    return JSONResponse(status_code=status_code, content={"data": payload})
