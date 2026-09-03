import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    idempotency_conflict,
    not_found,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.quality_gates import repository as repo
from app.modules.quality_gates.service import (
    PolicyCreateInput,
    PolicyPatchInput,
    create_policy_for_caller,
    get_policy_for_caller,
    list_policies_for_caller,
    patch_policy_for_caller,
)

router = APIRouter(prefix="/api/v1")

ModeLiteral = Literal["report_only", "blocking"]


class ThresholdsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_pass_rate: float
    max_p95_ms: float
    max_error_rate: float


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    thresholds: ThresholdsBody
    mode: ModeLiteral
    scope: dict[str, Any]
    confirm_blocking: bool | None = None


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    thresholds: ThresholdsBody | None = None
    mode: ModeLiteral | None = None
    scope: dict[str, Any] | None = None
    confirm_blocking: bool | None = None


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
    raise validation_failed(trace_id) from exc


@router.get("/quality-gate-policies")
async def api_140_list_policies(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID, Query()],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    mode: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_policies_for_caller(
            db,
            ctx,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
            mode=mode,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/quality-gate-policies/{policy_id}")
async def api_141_get_policy(
    request: Request,
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_policy_for_caller(db, ctx, policy_id=policy_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/quality-gate-policies", status_code=201)
async def api_142_create_policy(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(PolicyCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await create_policy_for_caller(
            db,
            ctx,
            body=PolicyCreateInput(
                project_id=body.project_id,
                thresholds={
                    "min_pass_rate": body.thresholds.min_pass_rate,
                    "max_p95_ms": body.thresholds.max_p95_ms,
                    "max_error_rate": body.thresholds.max_error_rate,
                },
                mode=body.mode,
                scope=body.scope,
                confirm_blocking=body.confirm_blocking,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.patch("/quality-gate-policies/{policy_id}")
async def api_143_patch_policy(
    request: Request,
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(PolicyPatch, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    thresholds = None
    if body.thresholds is not None:
        thresholds = {
            "min_pass_rate": body.thresholds.min_pass_rate,
            "max_p95_ms": body.thresholds.max_p95_ms,
            "max_error_rate": body.thresholds.max_error_rate,
        }
    try:
        payload = await patch_policy_for_caller(
            db,
            ctx,
            policy_id=policy_id,
            body=PolicyPatchInput(
                expected_version=body.expected_version,
                thresholds=thresholds,
                mode=body.mode,
                scope=body.scope,
                confirm_blocking=body.confirm_blocking,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload
