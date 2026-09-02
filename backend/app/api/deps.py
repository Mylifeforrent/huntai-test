import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import (
    forbidden,
    token_cannot_approve,
    token_project_forbidden,
    token_revoked,
    unauthenticated,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.service import SessionContext, load_session_context
from app.modules.integration_hub.service import authenticate_api_token_by_prefix


@dataclass(frozen=True)
class ApiTokenContext:
    organization_id: uuid.UUID
    user_id: uuid.UUID
    scopes: tuple[str, ...]
    project_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True)
class SessionOrToken:
    session: SessionContext | None
    token: ApiTokenContext | None

    @property
    def organization_id(self) -> uuid.UUID:
        if self.session is not None:
            return self.session.organization.id
        if self.token is not None:
            return self.token.organization_id
        raise RuntimeError("no auth context")

    @property
    def user_id(self) -> uuid.UUID | None:
        if self.session is not None:
            return self.session.user.id
        if self.token is not None:
            return self.token.user_id
        return None


@dataclass(frozen=True)
class OptionalSession:
    context: SessionContext | None
    raw_session_id: uuid.UUID | None


async def get_optional_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OptionalSession:
    cookie_name = settings.session_cookie_name
    raw_value = request.cookies.get(cookie_name)
    if raw_value is None:
        return OptionalSession(context=None, raw_session_id=None)
    try:
        session_id = uuid.UUID(raw_value)
    except ValueError:
        return OptionalSession(context=None, raw_session_id=None)

    auth_session = await repo.get_auth_session_by_id(db, session_id)
    if auth_session is None:
        return OptionalSession(context=None, raw_session_id=session_id)

    ctx = await load_session_context(db, auth_session)
    return OptionalSession(context=ctx, raw_session_id=session_id)


async def require_session(
    request: Request,
    optional: Annotated[OptionalSession, Depends(get_optional_session)],
) -> SessionContext:
    trace_id = get_trace_id(request)
    if optional.context is None:
        raise unauthenticated(trace_id)
    return optional.context


async def require_session_with_membership(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> SessionContext:
    trace_id = get_trace_id(request)
    count = await repo.count_project_memberships(
        db, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if count < 1:
        raise forbidden(trace_id, "No organization context")
    return ctx


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth is None:
        return None
    parts = auth.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_api_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    *,
    required_scope: str,
) -> ApiTokenContext:
    trace_id = get_trace_id(request)
    raw = _extract_bearer_token(request)
    if raw is None:
        raise unauthenticated(trace_id)
    token = await authenticate_api_token_by_prefix(db, raw_token=raw)
    if token is None:
        raise token_revoked(trace_id)
    scopes = list(token.scopes or [])
    if required_scope not in scopes:
        raise token_cannot_approve(trace_id, "Token scope not allowed")
    return ApiTokenContext(
        organization_id=token.organization_id,
        user_id=token.issued_to_user_id,
        scopes=tuple(scopes),
        project_ids=tuple(token.project_ids or []),
    )


async def require_session_or_token_read(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    optional: Annotated[OptionalSession, Depends(get_optional_session)],
) -> SessionOrToken:
    trace_id = get_trace_id(request)
    if optional.context is not None:
        return SessionOrToken(session=optional.context, token=None)
    raw = _extract_bearer_token(request)
    if raw is None:
        raise unauthenticated(trace_id)
    token = await authenticate_api_token_by_prefix(db, raw_token=raw)
    if token is None:
        raise token_revoked(trace_id)
    if "read" not in list(token.scopes or []):
        raise token_cannot_approve(trace_id, "Token scope not allowed")
    return SessionOrToken(
        session=None,
        token=ApiTokenContext(
            organization_id=token.organization_id,
            user_id=token.issued_to_user_id,
            scopes=tuple(token.scopes or []),
            project_ids=tuple(token.project_ids or []),
        ),
    )


def assert_token_project_allowed(
    token_ctx: ApiTokenContext, project_id: uuid.UUID, trace_id: str
) -> None:
    allowed = list(token_ctx.project_ids)
    if not allowed or project_id not in allowed:
        raise token_project_forbidden(trace_id)
