"""Copilot session routes (API-190…193)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    not_found,
    policy_deny,
    precondition_failed,
    quota_exceeded,
    unauthenticated,
    validation_failed,
)
from app.core.logging import get_trace_id
from app.modules.ai_governance import copilot_service
from app.modules.identity_tenancy.service import SessionContext

router = APIRouter(prefix="/api/v1")


class CopilotSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    selected_skill_version_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None


class CopilotMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


def _map_read_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "policy_kill":
        raise policy_deny(trace_id, "Copilot capability tightened (kill switch active)") from exc
    if code == "quota":
        raise quota_exceeded(trace_id, "AI token budget exhausted") from exc
    if code == "copilot_write":
        raise precondition_failed(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/copilot-sessions")
async def api_190_list_copilot_sessions(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    if not isinstance(ctx.user.id, uuid.UUID):
        raise unauthenticated(trace_id)
    payload = await copilot_service.list_sessions_for_caller(db, ctx, limit=limit)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.post("/copilot-sessions", status_code=201)
async def api_191_create_copilot_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    try:
        body = CopilotSessionCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc
    try:
        payload = await copilot_service.create_session_for_caller(
            db,
            ctx,
            title=body.title,
            project_id=body.project_id,
            selected_skill_version_id=body.selected_skill_version_id,
        )
    except ValueError as exc:
        await db.commit()
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/copilot-sessions/{session_id}")
async def api_193_get_copilot_session(
    request: Request,
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await copilot_service.get_session_for_caller(db, ctx, session_id=session_id)
    except ValueError as exc:
        await db.commit()
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/copilot-sessions/{session_id}/messages")
async def api_192_post_copilot_message(
    request: Request,
    session_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    try:
        body = CopilotMessageCreate.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc
    idempotency_key = request.headers.get("idempotency-key")
    try:
        payload = await copilot_service.post_message_for_caller(
            db,
            ctx,
            session_id=session_id,
            content=body.content,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        await db.commit()
        _map_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}
