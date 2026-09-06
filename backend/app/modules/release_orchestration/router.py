"""ReleaseTask API routes (API-150…155)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.db import get_db_session
from app.core.errors import (
    ext_read_failed,
    ext_unknown_result,
    forbidden,
    idempotency_conflict,
    not_found,
    precondition_failed,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.release_orchestration import repository as repo
from app.modules.release_orchestration import service

router = APIRouter(prefix="/api/v1")


class ReleaseTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    jira_version_ref: str


class ReleaseTaskRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    reason: str | None = None


class ReleaseTaskCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


def _parse_body(model: type[BaseModel], raw: bytes, trace_id: str) -> BaseModel:
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
    if code == "unknown_external":
        raise ext_unknown_result(trace_id) from exc
    if code == "ext_read":
        raise ext_read_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/release-tasks")
async def api_150_list_release_tasks(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[str, Query()],
    status: Annotated[
        Literal[
            "DRAFT",
            "PENDING_CONFIRM",
            "SUBMITTED",
            "READY",
            "FAILED_RETRYABLE",
            "CANCELLED",
        ]
        | None,
        Query(),
    ] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    try:
        payload = await service.list_release_tasks_for_caller(
            db, ctx, project_id=project_uuid, status=status
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/release-tasks/{release_task_id}")
async def api_151_get_release_task(
    request: Request,
    release_task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await service.get_release_task_for_caller(
            db, ctx, release_task_id=release_task_id
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/release-tasks/{release_task_id}/readiness")
async def api_155_get_readiness(
    request: Request,
    release_task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        task = await repo.get_release_task(
            db, organization_id=ctx.organization.id, release_task_id=release_task_id
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    if task is None:
        raise not_found(trace_id)
    try:
        await service._require_project(
            db, ctx, project_id=task.project_id, roles=service.READ_ROLES
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    payload = await service.build_readiness_projection(db, ctx, task=task)
    return {"data": payload}


@router.post("/release-tasks", status_code=201)
async def api_152_create_release_task(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ReleaseTaskCreate, raw, trace_id)
    assert isinstance(body, ReleaseTaskCreate)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await service.create_release_task_for_caller(
            db,
            ctx,
            project_id=body.project_id,
            jira_version_ref=body.jira_version_ref,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    task_id = payload["id"]
    background_tasks.add_task(
        service.advance_draft_to_pending_confirm,
        organization_id=ctx.organization.id,
        release_task_id=uuid.UUID(str(task_id)),
        actor_user_id=ctx.user.id,
    )
    return {"data": payload}


@router.post("/release-tasks/{release_task_id}/retries", status_code=202)
async def api_153_retry_release_task(
    request: Request,
    background_tasks: BackgroundTasks,
    release_task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ReleaseTaskRetry, raw, trace_id)
    assert isinstance(body, ReleaseTaskRetry)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await service.retry_release_task_for_caller(
            db,
            ctx,
            release_task_id=release_task_id,
            expected_version=body.expected_version,
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    background_tasks.add_task(
        service.prepare_after_retry,
        organization_id=ctx.organization.id,
        release_task_id=release_task_id,
        actor_user_id=ctx.user.id,
    )
    return {"data": payload}


@router.post("/release-tasks/{release_task_id}/cancel")
async def api_154_cancel_release_task(
    request: Request,
    release_task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(ReleaseTaskCancel, raw, trace_id)
    assert isinstance(body, ReleaseTaskCancel)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await service.cancel_release_task_for_caller(
            db,
            ctx,
            release_task_id=release_task_id,
            expected_version=body.expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return {"data": payload}
