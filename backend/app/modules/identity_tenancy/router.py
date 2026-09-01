import json
import uuid
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OptionalSession,
    get_optional_session,
    require_session,
    require_session_with_membership,
)
from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    idempotency_conflict,
    not_found,
    oidc_auth_failed,
    open_redirect,
    policy_deny,
    precondition_failed,
    validation_failed,
    version_conflict,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.service import (
    SessionContext,
    add_project_member,
    build_me_payload,
    build_organization_current,
    build_session_payload,
    complete_oidc_callback,
    get_project_overview,
    get_workbench_for_caller,
    list_members,
    list_projects,
    logout_session,
    patch_project_member_role,
    put_siem_export_for_caller,
    remove_project_member,
    require_idempotency_key,
    start_oidc_flow,
    tighten_capability_controls,
    validate_return_path,
)

router = APIRouter(prefix="/api/v1")

RoleLiteral = Literal["owner", "admin", "tester", "viewer"]


class ReauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_path: str | None = None


class ProjectMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    role: RoleLiteral
    expected_project_version: int | None = Field(default=None, ge=1)


class ProjectMemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RoleLiteral
    expected_project_version: int | None = Field(default=None, ge=1)


class ProjectMemberRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_project_version: int | None = Field(default=None, ge=1)


class CapabilityTightenTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["ability", "module", "connector", "global"]
    capability_id: str | None = None
    module: str | None = None
    connector_id: str | None = None


class CapabilityTightenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target: CapabilityTightenTarget
    reason: str | None = None


class SiemExportFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_types: list[str] | None = None
    include_denied_attempts: bool | None = None


class SiemExportPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    enabled: bool
    destination_connector_id: uuid.UUID | None = None
    filter: SiemExportFilter | None = None


FORBIDDEN_TIGHTEN_BODY_KEYS = frozenset({"direction", "restore", "loosen", "enabled"})


def _map_project_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code in {"validation", "invalid_cursor"}:
        raise validation_failed(trace_id) from exc
    if code == "version_conflict":
        raise version_conflict(trace_id) from exc
    if code == "state":
        raise precondition_failed(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
    if code == "policy_deny":
        raise policy_deny(trace_id) from exc
    raise validation_failed(trace_id) from exc


def _parse_body[T: BaseModel](model_type: type[T], raw: bytes, trace_id: str) -> T:
    try:
        return model_type.model_validate_json(raw if raw.strip() else b"{}")
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


@router.get("/auth/oidc/start")
async def api_001_oidc_start(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    return_path: Annotated[str | None, Query()] = None,
) -> dict[str, str]:
    trace_id = get_trace_id(request)
    try:
        validate_return_path(return_path)
    except ValueError:
        raise open_redirect(trace_id) from None

    result = await start_oidc_flow(db, settings, return_path=return_path)
    await db.commit()
    return result


@router.get("/auth/oidc/callback")
async def api_002_oidc_callback(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    optional: Annotated[OptionalSession, Depends(get_optional_session)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    trace_id = get_trace_id(request)
    if not code or not state:
        raise oidc_auth_failed(trace_id)

    existing_session = None
    if optional.raw_session_id is not None:
        existing_session = await repo.get_auth_session_by_id(db, optional.raw_session_id)

    try:
        auth_session, return_path = await complete_oidc_callback(
            db,
            settings,
            code=code,
            state=state,
            existing_session=existing_session,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "no_org_context":
            raise forbidden(trace_id, "No organization context") from exc
        raise oidc_auth_failed(trace_id) from exc

    await db.commit()
    redirect = RedirectResponse(url=return_path, status_code=302)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=str(auth_session.id),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite.value.lower(),  # type: ignore[arg-type]
        path="/",
    )
    return redirect


@router.post("/auth/session/logout", status_code=204)
async def api_003_logout(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    optional: Annotated[OptionalSession, Depends(get_optional_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    trace_id = get_trace_id(request)
    idempotency_key = request.headers.get("idempotency-key")
    body = await request.body()
    request_hash = repo.hash_request_body(body)

    try:
        await logout_session(
            db,
            ctx=optional.context,
            raw_session_id=optional.raw_session_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        if str(exc) == "idempotency_conflict":
            raise idempotency_conflict(trace_id) from exc
        raise

    await db.commit()
    response = Response(status_code=204)
    if optional.raw_session_id is not None:
        response.delete_cookie(
            key=settings.session_cookie_name,
            path="/",
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite=settings.session_cookie_samesite.value.lower(),  # type: ignore[arg-type]
        )
    return response


@router.post("/auth/reauth")
async def api_004_reauth(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    body: ReauthRequest | None = None,
) -> dict[str, object]:
    trace_id = get_trace_id(request)
    _ = ctx
    return_path = body.return_path if body is not None else None
    try:
        validate_return_path(return_path)
    except ValueError:
        raise open_redirect(trace_id) from None

    result = await start_oidc_flow(db, settings, return_path=return_path)
    await db.commit()
    return {
        "reauth_satisfied": False,
        "authorization_url": result["authorization_url"],
    }


@router.get("/me")
async def api_005_me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, object]:
    trace_id = get_trace_id(request)
    count = await repo.count_project_memberships(
        db, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if count < 1:
        raise forbidden(trace_id, "No organization context")

    memberships = await repo.list_memberships(
        db, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    return {"data": build_me_payload(ctx, memberships)}


@router.get("/workbench")
async def api_020_workbench(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_workbench_for_caller(db, ctx, project_id=project_id)
    except ValueError as exc:
        code = str(exc)
        if code == "forbidden":
            raise forbidden(trace_id) from exc
        if code == "not_found":
            raise not_found(trace_id) from exc
        raise validation_failed(trace_id) from exc
    return {"data": payload}


@router.get("/auth/session")
async def api_006_session(
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, object]:
    return build_session_payload(ctx)


@router.get("/organizations/current")
async def api_010_organization_current(
    ctx: Annotated[SessionContext, Depends(require_session_with_membership)],
) -> dict[str, object]:
    return {"data": build_organization_current(ctx.organization)}


@router.get("/projects")
async def api_011_list_projects(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        return await list_projects(db, ctx, cursor=cursor, limit=limit, q=q, sort=sort)
    except ValueError as exc:
        _map_project_error(trace_id, exc)


@router.get("/projects/{project_id}")
async def api_012_get_project(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: uuid.UUID,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        data = await get_project_overview(db, ctx, project_id=project_id)
    except ValueError as exc:
        _map_project_error(trace_id, exc)
    return {"data": data}


@router.get("/projects/{project_id}/members")
async def api_013_list_members(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: uuid.UUID,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        return await list_members(
            db, ctx, project_id=project_id, cursor=cursor, limit=limit, role=role
        )
    except ValueError as exc:
        _map_project_error(trace_id, exc)


@router.post("/projects/{project_id}/members")
async def api_014_add_member(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: uuid.UUID,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    request_hash = repo.hash_request_body(raw)
    body = _parse_body(ProjectMemberCreate, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
        data = await add_project_member(
            db,
            ctx,
            project_id=project_id,
            user_id=body.user_id,
            role=body.role,
            expected_project_version=body.expected_project_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_project_error(trace_id, exc)
    await db.commit()
    return {"data": data}


@router.patch("/projects/{project_id}/members/{user_id}")
async def api_015_patch_member(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    request_hash = repo.hash_request_body(raw)
    body = _parse_body(ProjectMemberPatch, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
        data = await patch_project_member_role(
            db,
            ctx,
            project_id=project_id,
            user_id=user_id,
            role=body.role,
            expected_project_version=body.expected_project_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_project_error(trace_id, exc)
    await db.commit()
    return {"data": data}


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
async def api_016_remove_member(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Response:
    trace_id = get_trace_id(request)
    raw = await request.body()
    request_hash = repo.hash_request_body(raw)
    expected_version: int | None = None
    if raw.strip():
        body = _parse_body(ProjectMemberRemove, raw, trace_id)
        expected_version = body.expected_project_version
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
        await remove_project_member(
            db,
            ctx,
            project_id=project_id,
            user_id=user_id,
            expected_project_version=expected_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_project_error(trace_id, exc)
    await db.commit()
    return Response(status_code=204)


@router.post("/organizations/current/capability-controls/tighten")
async def api_199_capability_tighten(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session_with_membership)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    request_hash = repo.hash_request_body(raw)
    try:
        parsed = json.loads(raw if raw.strip() else b"{}")
    except json.JSONDecodeError as exc:
        raise validation_failed(trace_id) from exc
    if not isinstance(parsed, dict):
        raise validation_failed(trace_id)
    for key in FORBIDDEN_TIGHTEN_BODY_KEYS:
        if key in parsed:
            raise validation_failed(trace_id)
    if parsed.get("enabled") is True:
        raise validation_failed(trace_id)
    try:
        body = CapabilityTightenRequest.model_validate(parsed)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    try:
        payload = await tighten_capability_controls(
            db,
            ctx,
            expected_version=body.expected_version,
            target=body.target.model_dump(exclude_none=True),
            reason=body.reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_project_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.put("/organizations/current/siem-export")
async def api_040_put_siem_export(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session_with_membership)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    request_hash = repo.hash_request_body(raw)
    body = _parse_body(SiemExportPutRequest, raw, trace_id)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    filter_payload = body.filter.model_dump(exclude_none=True) if body.filter is not None else None
    try:
        payload = await put_siem_export_for_caller(
            db,
            ctx,
            expected_version=body.expected_version,
            enabled=body.enabled,
            destination_connector_id=body.destination_connector_id,
            filter_payload=filter_payload,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_project_error(trace_id, exc)
    await db.commit()
    return {"data": payload}
