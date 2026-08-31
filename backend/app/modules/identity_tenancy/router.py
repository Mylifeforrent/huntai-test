from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    OptionalSession,
    get_optional_session,
    require_session,
    require_session_with_membership,
)
from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import forbidden, idempotency_conflict, oidc_auth_failed, open_redirect
from app.core.logging import get_trace_id
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.service import (
    SessionContext,
    build_me_payload,
    build_organization_current,
    build_session_payload,
    complete_oidc_callback,
    logout_session,
    start_oidc_flow,
    validate_return_path,
)

router = APIRouter(prefix="/api/v1")


class ReauthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_path: str | None = None


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
