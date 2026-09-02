import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import require_session
from app.core.db import get_db_session
from app.core.errors import (
    async_generation_failed,
    file_validation_failed,
    forbidden,
    idempotency_conflict,
    not_found,
    policy_deny,
    precondition_failed,
    quota_exceeded,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.ai_governance import repository as repo
from app.modules.ai_governance.a1_service import (
    GenerationCreateInput,
    create_generation_for_caller,
    get_generation_drafts_for_caller,
    get_generation_for_caller,
    run_generation_background,
)
from app.modules.ai_governance.service import (
    ModelRoutePutInput,
    connection_test_for_caller,
    get_cost_dashboard_for_caller,
    get_invocation_log_for_caller,
    list_invocation_logs_for_caller,
    list_model_routes_for_caller,
    put_model_route_for_caller,
)
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key

router = APIRouter(prefix="/api/v1")

DataClassificationLiteral = Literal["Public", "Internal", "Confidential", "Restricted"]
InvocationResultLiteral = Literal["ok", "degraded", "refused"]


class ModelRoutePutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    task_type: str
    data_classification: DataClassificationLiteral
    provider_allowlist: list[str]
    max_cost: Decimal
    fallback: dict[str, Any] | None = None
    require_prompt_version: bool = False
    require_structured_output: bool = False
    credential_bound: bool | None = None


class ConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


SourceTypeLiteral = Literal["openapi", "postman", "curl"]


class GenerationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    source_type: SourceTypeLiteral
    import_source_id: uuid.UUID | None = None
    inline_content: str | None = None
    case_type_policy: dict[str, Any] | None = None


def _map_read_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "invalid_cursor":
        raise validation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _map_command_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "file_validation":
        raise file_validation_failed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "policy_deny" or code == "policy":
        raise policy_deny(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    if code == "quota":
        raise quota_exceeded(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "async_failed":
        raise async_generation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _parse_json_model[T: BaseModel](raw: bytes, trace_id: str, model: type[T]) -> T:
    try:
        data = json.loads(raw if raw.strip() else b"{}")
        if not isinstance(data, dict):
            raise validation_failed(trace_id)
        return model.model_validate(data)
    except (json.JSONDecodeError, TypeError) as exc:
        raise validation_failed(trace_id) from exc
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


@router.get("/model-routes")
async def api_196_list_model_routes(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    task_type: Annotated[str | None, Query()] = None,
    data_classification: Annotated[DataClassificationLiteral | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_model_routes_for_caller(
            db,
            ctx,
            cursor=cursor,
            limit=limit,
            task_type=task_type,
            data_classification=data_classification,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.put("/model-routes/{model_route_id}")
async def api_197_put_model_route(
    request: Request,
    model_route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_json_model(raw, trace_id, ModelRoutePutRequest)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await put_model_route_for_caller(
            db,
            ctx,
            model_route_id=model_route_id,
            body=ModelRoutePutInput(
                expected_version=body.expected_version,
                task_type=body.task_type,
                data_classification=body.data_classification,
                provider_allowlist=body.provider_allowlist,
                max_cost=body.max_cost,
                fallback=body.fallback,
                require_prompt_version=body.require_prompt_version,
                require_structured_output=body.require_structured_output,
                credential_bound=body.credential_bound,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_command_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/model-routes/{model_route_id}/connection-tests")
async def api_198_connection_test(
    request: Request,
    model_route_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_json_model(raw, trace_id, ConnectionTestRequest)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await connection_test_for_caller(
            db,
            ctx,
            model_route_id=model_route_id,
            expected_version=body.expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_command_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/ai-invocation-logs")
async def api_184_list_invocation_logs(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    user_id: Annotated[uuid.UUID | None, Query()] = None,
    result: Annotated[InvocationResultLiteral | None, Query()] = None,
    model: Annotated[str | None, Query()] = None,
    copilot_session_id: Annotated[uuid.UUID | None, Query()] = None,
    created_from: Annotated[str | None, Query()] = None,
    created_to: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_invocation_logs_for_caller(
            db,
            ctx,
            cursor=cursor,
            limit=limit,
            user_id=user_id,
            result=result,
            model=model,
            copilot_session_id=copilot_session_id,
            created_from=_parse_datetime(created_from),
            created_to=_parse_datetime(created_to),
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/ai-invocation-logs/{log_id}")
async def api_185_get_invocation_log(
    request: Request,
    log_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_invocation_log_for_caller(db, ctx, log_id=log_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/ai/generations", status_code=202)
async def api_180_create_generation(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_json_model(raw, trace_id, GenerationCreateRequest)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload, accepted_new = await create_generation_for_caller(
            db,
            ctx,
            body=GenerationCreateInput(
                project_id=body.project_id,
                source_type=body.source_type,
                import_source_id=body.import_source_id,
                inline_content=body.inline_content,
                case_type_policy=body.case_type_policy,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_command_error(trace_id, exc)
    if accepted_new:
        generation_id = uuid.UUID(str(payload["data"]["generation_id"]))
        background_tasks.add_task(
            run_generation_background,
            organization_id=ctx.organization.id,
            user_id=ctx.user.id,
            generation_id=generation_id,
            source_type=body.source_type,
        )
    await db.commit()
    return payload


@router.get("/ai/generations/{generation_id}")
async def api_181_get_generation(
    request: Request,
    generation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_generation_for_caller(db, ctx, generation_id=generation_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/ai/generations/{generation_id}/drafts")
async def api_182_get_generation_drafts(
    request: Request,
    generation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_generation_drafts_for_caller(db, ctx, generation_id=generation_id)
    except ValueError as exc:
        await db.commit()
        _map_command_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


async def _generation_sse_events(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    generation_id: uuid.UUID,
) -> Any:
    import asyncio
    from datetime import UTC, datetime

    from app.core.db import get_session_factory
    from app.modules.identity_tenancy import query_port as identity_query

    factory = get_session_factory()
    sent_terminal = False
    for _ in range(40):
        async with factory() as session:
            row = await repo.get_a1_generation(
                session,
                organization_id=organization_id,
                generation_id=generation_id,
            )
            if row is None:
                break
            role = await identity_query.get_project_membership_role(
                session,
                organization_id=organization_id,
                project_id=row.project_id,
                user_id=user_id,
            )
            if role is None:
                break
            now = datetime.now(UTC).isoformat()
            if row.status in {"accepted", "running"}:
                event_type = "progress"
                data = {
                    "id": str(uuid.uuid4()),
                    "type": event_type,
                    "occurred_at": now,
                    "resource_type": "generation",
                    "resource_id": str(generation_id),
                    "progress_percent": 50 if row.status == "running" else 10,
                    "hint": "processing",
                }
                yield {"event": event_type, "data": json.dumps(data)}
                await asyncio.sleep(0.05)
                continue
            event_type = "degraded" if row.degraded else "progress"
            data = {
                "id": str(uuid.uuid4()),
                "type": event_type,
                "occurred_at": now,
                "resource_type": "generation",
                "resource_id": str(generation_id),
                "progress_percent": 100,
            }
            yield {"event": event_type, "data": json.dumps(data)}
            sent_terminal = True
            break
    if not sent_terminal:
        now = datetime.now(UTC).isoformat()
        yield {
            "event": "heartbeat",
            "data": json.dumps(
                {
                    "id": str(uuid.uuid4()),
                    "type": "heartbeat",
                    "occurred_at": now,
                    "resource_type": "generation",
                    "resource_id": str(generation_id),
                }
            ),
        }


@router.get("/ai/generations/{generation_id}/events")
async def api_211_generation_events(
    request: Request,
    generation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> EventSourceResponse:
    from app.modules.identity_tenancy import query_port as identity_query

    trace_id = get_trace_id(request)
    row = await repo.get_a1_generation(
        db,
        organization_id=ctx.organization.id,
        generation_id=generation_id,
    )
    if row is None:
        raise not_found(trace_id)
    role = await identity_query.get_project_membership_role(
        db,
        organization_id=ctx.organization.id,
        project_id=row.project_id,
        user_id=ctx.user.id,
    )
    if role is None:
        raise not_found(trace_id)
    await db.commit()
    return EventSourceResponse(
        _generation_sse_events(
            organization_id=ctx.organization.id,
            user_id=ctx.user.id,
            generation_id=generation_id,
        )
    )


@router.get("/ai/cost-dashboard")
async def api_183_cost_dashboard(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: Annotated[str | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    dimension: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    if from_ is None or to is None:
        raise validation_failed(trace_id)
    created_from = _parse_datetime(from_)
    created_to = _parse_datetime(to)
    if created_from is None or created_to is None:
        raise validation_failed(trace_id)
    _ = dimension
    try:
        payload = await get_cost_dashboard_for_caller(
            db,
            ctx,
            created_from=created_from,
            created_to=created_to,
            project_id=project_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}
