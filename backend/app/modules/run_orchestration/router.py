import json
import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    OptionalSession,
    SessionOrToken,
    _extract_bearer_token,
    get_optional_session,
    require_session,
    require_session_or_token_read,
)
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    idempotency_conflict,
    not_found,
    precondition_failed,
    token_cannot_approve,
    token_project_forbidden,
    token_revoked,
    unauthenticated,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.integration_hub.service import authenticate_api_token_by_prefix
from app.modules.run_orchestration import repository as repo
from app.modules.run_orchestration.command_port import cancel_external_ci_with_collect
from app.modules.run_orchestration.executor import run_test_run_background
from app.modules.run_orchestration.service import (
    cancel_test_run,
    get_command_receipt_for_caller,
    get_execution_options_for_caller,
    get_test_run_for_auth,
    get_test_run_for_caller,
    list_test_runs_for_auth,
    start_test_run_api_token,
    start_test_run_session,
)

router = APIRouter(prefix="/api/v1")

ExecutionSourceLiteral = Literal["script", "agent", "external_ci"]
TriggerTypeLiteral = Literal["manual", "schedule"]
TokenTriggerLiteral = Literal["api_token"]


class TestRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    env_id: uuid.UUID
    execution_source: ExecutionSourceLiteral
    case_ids: list[uuid.UUID] = Field(min_length=1)
    trigger_type: TriggerTypeLiteral | TokenTriggerLiteral | None = None
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
    if code == "token_project":
        raise token_project_forbidden(trace_id) from exc
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
    if code == "token_project":
        raise token_project_forbidden(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    raise validation_failed(trace_id) from exc


async def _queue_run_if_new(
    *,
    background_tasks: BackgroundTasks,
    organization_id: uuid.UUID,
    payload: dict[str, Any],
    accepted_new: bool,
) -> None:
    if not accepted_new:
        return
    run_id = uuid.UUID(str(payload["id"]))
    background_tasks.add_task(
        run_test_run_background,
        organization_id=organization_id,
        test_run_id=run_id,
    )


@router.get("/test-runs")
async def api_060_list_test_runs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[SessionOrToken, Depends(require_session_or_token_read)],
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
        payload = await list_test_runs_for_auth(
            db,
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
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/test-runs/{test_run_id}")
async def api_061_get_test_run(
    request: Request,
    test_run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[SessionOrToken, Depends(require_session_or_token_read)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_test_run_for_auth(db, auth, test_run_id=test_run_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.post("/test-runs")
async def api_062_080_start_test_run(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    optional: Annotated[OptionalSession, Depends(get_optional_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestRunCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    request_hash = repo.hash_request_body(raw)

    bearer = _extract_bearer_token(request)
    if bearer is not None:
        token = await authenticate_api_token_by_prefix(db, raw_token=bearer)
        if token is None:
            raise token_revoked(trace_id)
        if "execute" not in list(token.scopes or []):
            raise token_cannot_approve(trace_id, "Token missing execute scope")
        if body.trigger_type in {"manual", "schedule"}:
            raise validation_failed(trace_id)
        try:
            payload, accepted_new = await start_test_run_api_token(
                db,
                organization_id=token.organization_id,
                user_id=token.issued_to_user_id,
                token_project_ids=list(token.project_ids or []),
                body=body.model_dump(mode="json"),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        except ValueError as exc:
            await db.commit()
            _map_write_error(trace_id, exc)
        await _queue_run_if_new(
            background_tasks=background_tasks,
            organization_id=token.organization_id,
            payload=payload,
            accepted_new=accepted_new,
        )
        await db.commit()
        return {"data": payload}

    ctx = optional.context
    if ctx is None:
        raise unauthenticated(trace_id)
    if body.trigger_type == "api_token":
        raise validation_failed(trace_id)
    try:
        payload, accepted_new = await start_test_run_session(
            db,
            ctx,
            body=body.model_dump(mode="json"),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await _queue_run_if_new(
        background_tasks=background_tasks,
        organization_id=ctx.organization.id,
        payload=payload,
        accepted_new=accepted_new,
    )
    await db.commit()
    return {"data": payload}


@router.post("/test-runs/{test_run_id}/cancel")
async def api_063_cancel_test_run(
    request: Request,
    test_run_id: uuid.UUID,
    response: Response,
    background_tasks: BackgroundTasks,
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
        payload, status_code, ci_collect_run_id = await cancel_test_run(
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
    if ci_collect_run_id is not None:
        background_tasks.add_task(
            cancel_external_ci_with_collect,
            organization_id=ctx.organization.id,
            test_run_id=ci_collect_run_id,
        )
    response.status_code = status_code
    return {"data": payload}


@router.get("/projects/{project_id}/execution-options")
async def api_069_execution_options(
    request: Request,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    execution_source: Annotated[str | None, Query()] = None,
    plan_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_execution_options_for_caller(
            db,
            ctx,
            project_id=project_id,
            execution_source=execution_source,
            plan_id=plan_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/command-receipts/{receipt_id}")
async def api_071_get_command_receipt(
    request: Request,
    receipt_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[SessionOrToken, Depends(require_session_or_token_read)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    user_id = auth.user_id
    if user_id is None:
        raise unauthenticated(trace_id)
    try:
        payload = await get_command_receipt_for_caller(
            db,
            organization_id=auth.organization_id,
            user_id=user_id,
            receipt_id=receipt_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


async def _test_run_sse_events(
    *,
    request: Request,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    test_run_id: uuid.UUID,
) -> Any:
    import asyncio
    from datetime import UTC, datetime

    from app.core.db import get_session_factory
    from app.modules.identity_tenancy import query_port as identity_query

    factory = get_session_factory()
    seq = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            async with factory() as session:
                run = await repo.get_test_run(
                    session,
                    organization_id=organization_id,
                    test_run_id=test_run_id,
                )
                if run is None:
                    await session.commit()
                    break
                role = await identity_query.get_project_membership_role(
                    session,
                    organization_id=organization_id,
                    project_id=run.project_id,
                    user_id=user_id,
                )
                if role is None:
                    await session.commit()
                    break
                status = run.status
                progress = 10 if status == "PENDING" else 30 if status == "VALIDATING" else 70
                if status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"}:
                    progress = 100
                await session.commit()
            seq += 1
            now = datetime.now(UTC).isoformat()
            yield {
                "event": "progress",
                "id": str(seq),
                "data": json.dumps(
                    {
                        "id": str(seq),
                        "type": "progress",
                        "resource_type": "test_run",
                        "resource_id": str(test_run_id),
                        "progress_percent": progress,
                        "hint": status.lower(),
                        "occurred_at": now,
                    }
                ),
            }
            if status in {"SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"}:
                yield {
                    "event": "resource_changed",
                    "id": str(seq + 1),
                    "data": json.dumps(
                        {
                            "id": str(seq + 1),
                            "type": "resource_changed",
                            "resource_type": "test_run",
                            "resource_id": str(test_run_id),
                            "hint": "status_may_have_changed",
                            "occurred_at": now,
                        }
                    ),
                }
                break
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        return


@router.get("/test-runs/{test_run_id}/events")
async def api_210_test_run_events(
    request: Request,
    test_run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> EventSourceResponse:
    trace_id = get_trace_id(request)
    try:
        await get_test_run_for_caller(db, ctx, test_run_id=test_run_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return EventSourceResponse(
        _test_run_sse_events(
            request=request,
            organization_id=ctx.organization.id,
            user_id=ctx.user.id,
            test_run_id=test_run_id,
        )
    )
