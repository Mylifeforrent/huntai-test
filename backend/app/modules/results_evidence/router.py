import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionOrToken, require_session, require_session_or_token_read
from app.core.db import get_db_session
from app.core.errors import (
    file_validation_failed,
    forbidden,
    idempotency_conflict,
    not_found,
    policy_deny,
    precondition_failed,
    validation_failed,
)
from app.core.logging import get_trace_id
from app.modules.identity_tenancy.service import SessionContext, require_idempotency_key
from app.modules.results_evidence import repository as repo
from app.modules.results_evidence.artifacts_service import (
    get_artifact_metadata_for_caller,
    read_artifact_content_for_caller,
)
from app.modules.results_evidence.case_results_service import (
    get_case_result_for_caller,
    list_case_results_for_caller,
    list_step_runs_for_caller,
)
from app.modules.results_evidence.cluster_service import (
    correct_failure_cluster_for_caller,
    get_failure_cluster_for_caller,
    list_failure_clusters_for_caller,
    list_similar_failure_clusters_for_caller,
)
from app.modules.results_evidence.service import (
    get_audit_event_for_caller,
    list_audit_events_for_caller,
)

router = APIRouter(prefix="/api/v1")


class FailureClusterCorrectionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["category", "blocking_judgment", "root_cause"]
    old: str | None = None
    new: str | None


class FailureClusterCorrectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrections: list[FailureClusterCorrectionItem] = Field(min_length=1)


def _parse_body(model: type[BaseModel], raw: bytes, trace_id: str) -> BaseModel:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_failed(trace_id) from exc


def _map_write_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "forbidden":
        raise forbidden(trace_id) from exc
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code in {"validation", "invalid_cursor"}:
        raise validation_failed(trace_id) from exc
    if code == "idempotency_conflict":
        raise idempotency_conflict(trace_id) from exc
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


def _parse_uuid(value: str | None, trace_id: str) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise validation_failed(trace_id) from exc


def _parse_datetime(value: str | None, trace_id: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise validation_failed(trace_id) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


@router.get("/audit-events")
async def api_024_list_audit_events(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    actor_user_id: Annotated[str | None, Query()] = None,
    request_hash: Annotated[str | None, Query()] = None,
    approval_id: Annotated[str | None, Query()] = None,
    approval_bound_hash: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    resource_id: Annotated[str | None, Query()] = None,
    project_id: Annotated[str | None, Query()] = None,
    external_request_id: Annotated[str | None, Query()] = None,
    created_from: Annotated[str | None, Query()] = None,
    created_to: Annotated[str | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_audit_events_for_caller(
            db,
            ctx,
            cursor=cursor,
            limit=limit,
            sort=sort,
            actor_user_id=_parse_uuid(actor_user_id, trace_id),
            request_hash=request_hash,
            approval_id=_parse_uuid(approval_id, trace_id),
            approval_bound_hash=approval_bound_hash,
            resource_type=resource_type,
            resource_id=_parse_uuid(resource_id, trace_id),
            project_id=_parse_uuid(project_id, trace_id),
            external_request_id=external_request_id,
            created_from=_parse_datetime(created_from, trace_id),
            created_to=_parse_datetime(created_to, trace_id),
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/audit-events/{audit_event_id}")
async def api_025_get_audit_event(
    request: Request,
    audit_event_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_audit_event_for_caller(
            db,
            ctx,
            audit_event_id=audit_event_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


def _map_artifact_error(trace_id: str, exc: ValueError) -> NoReturn:
    code = str(exc)
    if code == "not_found":
        raise not_found(trace_id) from exc
    if code == "policy_deny":
        raise policy_deny(trace_id) from exc
    if code == "not_ready":
        raise precondition_failed(trace_id) from exc
    if code == "checksum_mismatch":
        raise file_validation_failed(trace_id) from exc
    raise validation_failed(trace_id) from exc


@router.get("/artifacts/{artifact_id}")
async def api_220_get_artifact(
    request: Request,
    artifact_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_artifact_metadata_for_caller(
            db,
            ctx,
            artifact_id=artifact_id,
        )
    except ValueError as exc:
        _map_artifact_error(trace_id, exc)
    return {"data": payload}


@router.get("/artifacts/{artifact_id}/content")
async def api_221_get_artifact_content(
    request: Request,
    artifact_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> Response:
    trace_id = get_trace_id(request)
    try:
        data, mime_type, filename = await read_artifact_content_for_caller(
            db,
            ctx,
            artifact_id=artifact_id,
        )
    except ValueError as exc:
        _map_artifact_error(trace_id, exc)
    await db.commit()
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/test-runs/{test_run_id}/case-results")
async def api_064_list_case_results(
    request: Request,
    test_run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[SessionOrToken, Depends(require_session_or_token_read)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    outcome: Annotated[str | None, Query()] = None,
    is_late: Annotated[bool | None, Query()] = None,
    is_partial: Annotated[bool | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_case_results_for_caller(
            db,
            auth,
            test_run_id=test_run_id,
            outcome=outcome,
            is_late=is_late,
            is_partial=is_partial,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/case-results/{case_result_id}")
async def api_065_get_case_result(
    request: Request,
    case_result_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    auth: Annotated[SessionOrToken, Depends(require_session_or_token_read)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_case_result_for_caller(
            db,
            auth,
            case_result_id=case_result_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/case-results/{case_result_id}/step-runs")
async def api_066_list_step_runs(
    request: Request,
    case_result_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_step_runs_for_caller(
            db,
            ctx,
            case_result_id=case_result_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}


@router.get("/test-runs/{test_run_id}/failure-clusters")
async def api_130_list_failure_clusters(
    request: Request,
    test_run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_failure_clusters_for_caller(
            db,
            ctx,
            test_run_id=test_run_id,
            category=category,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.get("/failure-clusters/{failure_cluster_id}")
async def api_131_get_failure_cluster(
    request: Request,
    failure_cluster_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await get_failure_cluster_for_caller(
            db,
            ctx,
            failure_cluster_id=failure_cluster_id,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": payload}


@router.patch("/failure-clusters/{failure_cluster_id}")
async def api_132_correct_failure_cluster(
    request: Request,
    failure_cluster_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    raw = await request.body()
    body = _parse_body(FailureClusterCorrectBody, raw, trace_id)
    assert isinstance(body, FailureClusterCorrectBody)
    try:
        idempotency_key = require_idempotency_key(request.headers.get("idempotency-key"))
    except ValueError:
        raise validation_failed(trace_id) from None
    request_hash = repo.hash_request_body(raw)
    try:
        payload = await correct_failure_cluster_for_caller(
            db,
            ctx,
            failure_cluster_id=failure_cluster_id,
            corrections=[item.model_dump(exclude_unset=True) for item in body.corrections],
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    except ValueError as exc:
        await db.commit()
        _map_write_error(trace_id, exc)
    await db.commit()
    return payload


@router.get("/failure-clusters/{failure_cluster_id}/similar")
async def api_133_list_similar_failure_clusters(
    request: Request,
    failure_cluster_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    ctx: Annotated[SessionContext, Depends(require_session)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    trace_id = get_trace_id(request)
    try:
        payload = await list_similar_failure_clusters_for_caller(
            db,
            ctx,
            failure_cluster_id=failure_cluster_id,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        _map_read_error(trace_id, exc)
    return {"data": {"items": payload["items"]}, "page": payload["page"]}
