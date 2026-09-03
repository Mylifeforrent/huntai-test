import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

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
    schema_validation_failed,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.test_assets import repository as repo
from app.modules.test_assets.service import (
    TestCaseCreateInput,
    TestCasePatchInput,
    TestPlanCaseIdsInput,
    TestPlanCreateInput,
    TestPlanPatchInput,
    TestPlanScheduleInput,
    create_test_case_draft_for_caller,
    create_test_plan_for_caller,
    get_import_source_for_caller,
    get_test_case_for_caller,
    get_test_plan_for_caller,
    list_test_cases_for_caller,
    list_test_plans_for_caller,
    patch_test_case_draft_for_caller,
    patch_test_plan_for_caller,
    put_test_plan_case_ids_for_caller,
    put_test_plan_schedule_for_caller,
    register_import_source_for_caller,
    review_test_case_for_caller,
    rollback_test_case_for_caller,
    submit_review_for_caller,
)

router = APIRouter(prefix="/api/v1")

CaseTypeLiteral = Literal["api", "web", "performance", "referenced"]
ExecutionModeLiteral = Literal["script", "agent"]
PriorityLiteral = Literal["P0", "P1", "P2", "P3"]
SourceTypeLiteral = Literal["openapi", "postman", "curl"]
ReviewDecisionLiteral = Literal["approve", "reject"]


class ImportSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    source_type: SourceTypeLiteral
    inline_content: str | None = None
    object_key: str | None = None
    original_filename: str | None = None


class TestCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    case_type: CaseTypeLiteral
    execution_mode: ExecutionModeLiteral
    title: str
    generation_id: uuid.UUID | None = None
    priority: PriorityLiteral | None = None
    tags: list[str] | None = None
    drafts: list[dict[str, Any]] | None = None
    job_binding: dict[str, Any] | None = None
    jira_story_key: str | None = None
    script: str | None = None


class TestCasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    title: str | None = None
    priority: PriorityLiteral | None = None
    tags: list[str] | None = None
    drafts: list[dict[str, Any]] | None = None
    job_binding: dict[str, Any] | None = None
    jira_story_key: str | None = None
    script: str | None = None


class SubmitReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    decision: ReviewDecisionLiteral
    jira_story_key: str | None = None
    reason: str | None = None


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target_version_id: uuid.UUID
    reason: str | None = None


class TestPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    name: str
    jira_fix_version: str | None = None


class TestPlanPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = None
    jira_fix_version: str | None = None


class TestPlanCaseIdsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    case_ids: list[uuid.UUID]


class TestPlanSchedulePut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    enabled: bool | None = None
    schedule: dict[str, Any] | None = None
    env_id: uuid.UUID | None = None


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
    if code == "file_validation":
        raise file_validation_failed(trace_id) from exc
    if code == "schema_validation":
        raise schema_validation_failed(trace_id) from exc
    if code == "policy" or code == "policy_deny":
        raise policy_deny(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    if code == "quota":
        raise quota_exceeded(trace_id) from exc
    if code == "async_failed":
        raise async_generation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/test-cases")
async def api_030_list_test_cases(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID, Query()],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    lifecycle_status: Annotated[str | None, Query()] = None,
    validity: Annotated[str | None, Query()] = None,
    tags: Annotated[str | None, Query()] = None,
    case_type: Annotated[str | None, Query()] = None,
    execution_mode: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_test_cases_for_caller(
            db,
            ctx,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
            lifecycle_status=lifecycle_status,
            validity=validity,
            tags=tags,
            case_type=case_type,
            execution_mode=execution_mode,
            priority=priority,
            q=q,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/test-cases/{test_case_id}")
async def api_031_get_test_case(
    request: Request,
    test_case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_test_case_for_caller(db, ctx, test_case_id=test_case_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/test-cases", status_code=201)
async def api_032_create_test_case(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestCaseCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await create_test_case_draft_for_caller(
            db,
            ctx,
            body=TestCaseCreateInput(
                project_id=body.project_id,
                case_type=body.case_type,
                execution_mode=body.execution_mode,
                title=body.title,
                generation_id=body.generation_id,
                priority=body.priority,
                tags=body.tags,
                drafts=body.drafts,
                job_binding=body.job_binding,
                jira_story_key=body.jira_story_key,
                script=body.script,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.patch("/test-cases/{test_case_id}")
async def api_033_patch_test_case(
    request: Request,
    test_case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestCasePatch, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await patch_test_case_draft_for_caller(
            db,
            ctx,
            test_case_id=test_case_id,
            body=TestCasePatchInput(
                expected_version=body.expected_version,
                title=body.title,
                priority=body.priority,
                tags=body.tags,
                drafts=body.drafts,
                job_binding=body.job_binding,
                jira_story_key=body.jira_story_key,
                script=body.script,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.post("/test-cases/{test_case_id}/submit-review")
async def api_034_submit_review(
    request: Request,
    test_case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(SubmitReviewBody, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await submit_review_for_caller(
            db,
            ctx,
            test_case_id=test_case_id,
            expected_version=body.expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.post("/test-cases/{test_case_id}/review")
async def api_035_review_test_case(
    request: Request,
    test_case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ReviewBody, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await review_test_case_for_caller(
            db,
            ctx,
            test_case_id=test_case_id,
            expected_version=body.expected_version,
            decision=body.decision,
            jira_story_key=body.jira_story_key,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.post("/test-cases/{test_case_id}/rollback")
async def api_039_rollback_test_case(
    request: Request,
    test_case_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(RollbackBody, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await rollback_test_case_for_caller(
            db,
            ctx,
            test_case_id=test_case_id,
            expected_version=body.expected_version,
            target_version_id=body.target_version_id,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.get("/test-plans")
async def api_050_list_test_plans(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID, Query()],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_test_plans_for_caller(
            db,
            ctx,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
            q=q,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/test-plans/{test_plan_id}")
async def api_051_get_test_plan(
    request: Request,
    test_plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_test_plan_for_caller(db, ctx, test_plan_id=test_plan_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/test-plans", status_code=201)
async def api_052_create_test_plan(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestPlanCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await create_test_plan_for_caller(
            db,
            ctx,
            body=TestPlanCreateInput(
                project_id=body.project_id,
                name=body.name,
                jira_fix_version=body.jira_fix_version,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.patch("/test-plans/{test_plan_id}")
async def api_053_patch_test_plan(
    request: Request,
    test_plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestPlanPatch, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await patch_test_plan_for_caller(
            db,
            ctx,
            test_plan_id=test_plan_id,
            body=TestPlanPatchInput(
                expected_version=body.expected_version,
                name=body.name,
                jira_fix_version=body.jira_fix_version,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.put("/test-plans/{test_plan_id}/case-ids")
async def api_054_put_test_plan_case_ids(
    request: Request,
    test_plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestPlanCaseIdsPut, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await put_test_plan_case_ids_for_caller(
            db,
            ctx,
            test_plan_id=test_plan_id,
            body=TestPlanCaseIdsInput(
                expected_version=body.expected_version,
                case_ids=body.case_ids,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.put("/test-plans/{test_plan_id}/schedule")
async def api_055_put_test_plan_schedule(
    request: Request,
    test_plan_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(TestPlanSchedulePut, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await put_test_plan_schedule_for_caller(
            db,
            ctx,
            test_plan_id=test_plan_id,
            body=TestPlanScheduleInput(
                expected_version=body.expected_version,
                enabled=body.enabled,
                schedule=body.schedule,
                env_id=body.env_id,
            ),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.get("/import-sources/{source_id}")
async def api_204_get_import_source(
    request: Request,
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_import_source_for_caller(db, ctx, source_id=source_id)
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/import-sources", status_code=201)
async def api_205_register_import_source(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ImportSourceCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await register_import_source_for_caller(
            db,
            ctx,
            project_id=body.project_id,
            source_type=body.source_type,
            inline_content=body.inline_content,
            object_key=body.object_key,
            original_filename=body.original_filename,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload
