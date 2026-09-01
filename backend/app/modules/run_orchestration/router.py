import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    idempotency_conflict,
    not_found,
    precondition_failed,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.service import (
    cancel_test_run,
    get_test_run_for_caller,
    list_test_runs_for_caller,
    start_test_run_session,
)

router = APIRouter(prefix="/api/v1")

ExecutionSourceLiteral = Literal["script", "agent", "external_ci"]
TriggerTypeLiteral = Literal["manual", "schedule"]


class TestRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    env_id: uuid.UUID
    execution_source: ExecutionSourceLiteral
    case_ids: list[uuid.UUID] = Field(min_length=1)
    trigger_type: TriggerTypeLiteral = "manual"
    plan_id: uuid.UUID | None = None
    params: dict[str, Any] | None = None
    expected_env_version: int | None = Field(default=None, ge=1)
    preview_id: uuid.UUID | None = None
    approval_request_id: uuid.UUID | None = None


class TestRunCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = None


def _parse_body[TModel: BaseModel](model: type[TModel], raw: bytes, trace_id: str) -> TModel:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


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
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/test-runs")
async def api_060_list_test_runs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    execution_source: Annotated[str | None, Query()] = None,
    trigger_type: Annotated[str | None, Query()] = None,
    plan_id: Annotated[uuid.UUID | None, Query()] = None,
    env_id: Annotated[uuid.UUID | None, Query()] = None,
    include_waiting: Annotated[bool, Query()] = True,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_test_runs_for_caller(
            db,
            ctx,
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
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/test-runs/{test_run_id}")
async def api_061_get_test_run(
    request: Request,
    test_run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_test_run_for_caller(db, ctx, test_run_id=test_run_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.post("/test-runs")
async def api_062_start_test_run(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestRunCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await start_test_run_session(
            db,
            ctx,
            body=body.model_dump(mode="json"),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/test-runs/{test_run_id}/cancel")
async def api_063_cancel_test_run(
    request: Request,
    test_run_id: uuid.UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestRunCancel, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)
    try:
        payload, status_code = await cancel_test_run(
            db,
            ctx,
            test_run_id=test_run_id,
            expected_version=body.expected_version,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    response.status_code = status_code
    return {"data": payload}
