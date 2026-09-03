import json
import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session
from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import (
    approval_expired,
    forbidden,
    four_eyes_violation,
    idempotency_conflict,
    not_found,
    param_hash_invalidated,
    policy_deny,
    policy_undeclared,
    precondition_failed,
    require_reauth,
    state_consumed,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.approval_policy import repository as repo
from app.modules.approval_policy.service import (
    FORBIDDEN_BODY_KEYS,
    ActionPreviewInput,
    _validate_payload_secrets,
    create_action_preview,
    get_action_preview_for_caller,
    get_approval_request_for_caller,
    list_approval_requests_for_caller,
    resubmit_approval_request,
    submit_approval_decision,
)
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key

router = APIRouter(prefix="/api/v1")

ActionTypeLiteral = Literal[
    "jira_write",
    "heal_apply",
    "perf_high_risk",
    "release_push",
    "env_register",
    "agent_tool_action",
    "gate_waiver",
    "kill_switch_restore",
    "copilot_write",
]

ListActionTypeLiteral = Literal[
    "jira_write",
    "heal_apply",
    "perf_high_risk",
    "release_push",
    "env_register",
    "agent_tool_action",
    "gate_waiver",
    "kill_switch_restore",
]

StatusLiteral = Literal[
    "CREATED",
    "PENDING",
    "APPROVED",
    "EXECUTED",
    "REJECTED",
    "EXPIRED",
]

PerspectiveLiteral = Literal["inbox", "initiated", "all"]


class ActionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionTypeLiteral
    target_object_type: str
    target_object_id: uuid.UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID | None = None
    expected_target_version: int | None = Field(default=None, ge=1)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reason: str | None = None
    expected_version: int = Field(ge=1)


class ApprovalResubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    expected_target_version: int | None = Field(default=None, ge=1)
    expected_origin_version: int | None = Field(default=None, ge=1)


def _map_preview_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    if code == "require_reauth":
        raise require_reauth(trace_id) from exc
    if code == "policy_undeclared":
        raise policy_undeclared(trace_id) from exc
    if code == "policy_deny":
        raise policy_deny(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _map_approval_read_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "invalid_cursor":
        raise validation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _map_decision_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "state":
        raise state_consumed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "four_eyes":
        raise four_eyes_violation(trace_id) from exc
    if code == "param_hash":
        raise param_hash_invalidated(trace_id) from exc
    if code == "approval_expired":
        raise approval_expired(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _map_resubmission_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "validation":
        raise validation_failed(trace_id) from exc
    if code == "state":
        raise state_consumed(trace_id) from exc
    if code == "version":
        raise version_conflict(trace_id) from exc
    if code == "require_reauth":
        raise require_reauth(trace_id) from exc
    if code == "policy_undeclared":
        raise policy_undeclared(trace_id) from exc
    if code == "policy_deny":
        raise policy_deny(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _parse_body(raw: bytes, trace_id: str) -> ActionPreviewRequest:
    try:
        data = json.loads(raw if raw.strip() else b"{}")
        if not isinstance(data, dict):
            raise validation_failed(trace_id)
        for key in FORBIDDEN_BODY_KEYS:
            if key in data:
                raise validation_failed(trace_id)
        return ActionPreviewRequest.model_validate(data)
    except (json.JSONDecodeError, TypeError) as exc:
        raise validation_failed(trace_id) from exc
    except ValidationError as exc:
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


@router.get("/approval-requests")
async def api_110_list_approval_requests(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    status: Annotated[StatusLiteral | None, Query()] = None,
    action_type: Annotated[ListActionTypeLiteral | None, Query()] = None,
    perspective: Annotated[PerspectiveLiteral | None, Query()] = None,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
    target_object_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_approval_requests_for_caller(
            db,
            ctx,
            cursor=cursor,
            limit=limit,
            status=status,
            action_type=action_type,
            perspective=perspective,
            project_id=project_id,
            target_object_id=target_object_id,
        )
    except ValueError as exc:
        _map_approval_read_error(trace_id, exc)
    await db.commit()
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/approval-requests/{approval_request_id}")
async def api_111_get_approval_request(
    request: Request,
    approval_request_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_approval_request_for_caller(
            db,
            ctx,
            approval_request_id=approval_request_id,
        )
    except ValueError as exc:
        _map_approval_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/action-previews/{preview_id}")
async def api_121_get_action_preview(
    request: Request,
    preview_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_action_preview_for_caller(
            db,
            ctx,
            preview_id=preview_id,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "approval_expired":
            raise approval_expired(trace_id) from exc
        _map_approval_read_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/approval-requests/{approval_request_id}/decisions")
async def api_112_approval_decision(
    request: Request,
    approval_request_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_json_model(raw, trace_id, ApprovalDecisionRequest)

    idempotency_key = request.headers.get("idempotency-key")
    request_hash = repo.hash_request_body(raw) if raw else None

    try:
        payload = await submit_approval_decision(
            db,
            ctx,
            approval_request_id=approval_request_id,
            decision=body.decision,
            reason=body.reason,
            expected_version=body.expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_decision_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/approval-requests/{approval_request_id}/resubmissions")
async def api_113_approval_resubmission(
    request: Request,
    approval_request_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_json_model(raw, trace_id, ApprovalResubmissionRequest)
    try:
        _validate_payload_secrets(body.payload)
    except ValueError:
        raise validation_failed(trace_id) from None

    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None

    request_hash = repo.hash_request_body(raw)
    try:
        payload = await resubmit_approval_request(
            db,
            ctx,
            settings,
            approval_request_id=approval_request_id,
            payload=body.payload,
            expected_target_version=body.expected_target_version,
            expected_origin_version=body.expected_origin_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_resubmission_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.post("/action-previews")
async def api_120_action_previews(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(raw, trace_id)
    try:
        _validate_payload_secrets(body.payload)
    except ValueError:
        raise validation_failed(trace_id) from None

    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None

    request_hash = repo.hash_request_body(raw)
    preview_input = ActionPreviewInput(
        action_type=body.action_type,
        target_object_type=body.target_object_type,
        target_object_id=body.target_object_id,
        payload=body.payload,
        project_id=body.project_id,
        expected_target_version=body.expected_target_version,
    )

    try:
        payload = await create_action_preview(
            db,
            ctx,
            settings,
            preview_input=preview_input,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_preview_error(trace_id, exc)

    await db.commit()
    return {"data": payload}
