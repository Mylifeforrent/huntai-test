import json
import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Request
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
)
from app.core.logging import get_trace_id
from app.modules.approval_policy import repository as repo
from app.modules.approval_policy.service import (
    FORBIDDEN_BODY_KEYS,
    ActionPreviewInput,
    _validate_payload_secrets,
    create_action_preview,
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


class ActionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionTypeLiteral
    target_object_type: str
    target_object_id: uuid.UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    project_id: uuid.UUID | None = None
    expected_target_version: int | None = Field(default=None, ge=1)


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
