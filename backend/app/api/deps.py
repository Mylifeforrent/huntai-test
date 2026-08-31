import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_db_session
from app.core.errors import forbidden, unauthenticated
from app.core.logging import get_trace_id
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.service import SessionContext, load_session_context


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
