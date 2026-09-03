import uuid
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_session, require_session_with_membership
from app.core.db import get_db_session
from app.core.errors import not_found, validation_failed
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quota_governance.service import (
    get_current_quota_for_caller,
    get_project_quota_view_for_caller,
)

router = APIRouter(prefix="/api/v1")


def _map_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/org-quotas/current")
async def api_017_org_quota_current(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session_with_membership)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_current_quota_for_caller(db, ctx)
    except ValueError as exc:
        _map_error(trace_id, exc)
    await db.commit()
    return {"data": payload}


@router.get("/projects/{project_id}/quota-view")
async def api_018_project_quota_view(
    request: Request,
    project_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_project_quota_view_for_caller(db, ctx, project_id=project_id)
    except ValueError as exc:
        _map_error(trace_id, exc)
    await db.commit()
    return {"data": payload}
