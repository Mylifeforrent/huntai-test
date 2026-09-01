import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry.models import (
    CommandIdempotencyRecord,
    ExecutionEnvironment,
    JobContract,
)


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def encode_created_id_cursor(*, created_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_created_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return created_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


async def get_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
) -> CommandIdempotencyRecord | None:
    result = await session.execute(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.organization_id == organization_id,
            CommandIdempotencyRecord.command_type == command_type,
            CommandIdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def create_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
    request_hash: str,
    response_ref: dict[str, Any],
    created_by: uuid.UUID | None,
    created_at: datetime,
) -> CommandIdempotencyRecord:
    record = CommandIdempotencyRecord(
        id=uuid.uuid4(),
        organization_id=organization_id,
        command_type=command_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response_ref,
        created_at=created_at,
        created_by=created_by,
    )
    session.add(record)
    await session.flush()
    return record


async def get_environment(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    environment_id: uuid.UUID,
    for_update: bool = False,
) -> ExecutionEnvironment | None:
    query = select(ExecutionEnvironment).where(
        ExecutionEnvironment.organization_id == organization_id,
        ExecutionEnvironment.id == environment_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_environments(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    env_type: str | None = None,
    status: str | None = None,
    visible_project_ids: list[uuid.UUID] | None = None,
    bound_project_id: uuid.UUID | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[ExecutionEnvironment]:
    query = (
        select(ExecutionEnvironment)
        .where(ExecutionEnvironment.organization_id == organization_id)
        .order_by(ExecutionEnvironment.created_at.desc(), ExecutionEnvironment.id.desc())
    )
    if env_type is not None:
        query = query.where(ExecutionEnvironment.env_type == env_type)
    if status is not None:
        query = query.where(ExecutionEnvironment.status == status)
    if visible_project_ids is not None:
        query = query.where(
            or_(
                ExecutionEnvironment.scope_level == "organization",
                and_(
                    ExecutionEnvironment.scope_level == "project",
                    ExecutionEnvironment.project_id.in_(visible_project_ids),
                ),
            )
        )
    if bound_project_id is not None:
        query = query.where(
            or_(
                ExecutionEnvironment.scope_level == "organization",
                and_(
                    ExecutionEnvironment.scope_level == "project",
                    ExecutionEnvironment.project_id == bound_project_id,
                ),
            )
        )
    if project_id is not None:
        query = query.where(
            or_(
                ExecutionEnvironment.scope_level == "organization",
                ExecutionEnvironment.project_id == project_id,
            )
        )
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                ExecutionEnvironment.created_at < cursor_created_at,
                and_(
                    ExecutionEnvironment.created_at == cursor_created_at,
                    ExecutionEnvironment.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_environment(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    env_type: str,
    name: str,
    endpoint: str | None,
    credential_ref: str | None,
    scope_level: str,
    project_id: uuid.UUID | None,
    standing_auth_metadata: dict[str, Any] | None = None,
) -> ExecutionEnvironment:
    env = ExecutionEnvironment(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        env_type=env_type,
        name=name,
        endpoint=endpoint,
        credential_ref=credential_ref,
        status="PENDING_APPROVAL",
        health_status=None,
        capacity=None,
        scope_level=scope_level,
        standing_auth_metadata=standing_auth_metadata,
        config_version=1,
        project_id=project_id,
    )
    session.add(env)
    await session.flush()
    return env


async def create_job_contract(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    execution_environment_id: uuid.UUID,
    job_id: str,
    params_schema_ref: str | None,
    params_schema: dict[str, Any] | None,
    artifact_manifest: dict[str, Any] | None,
    report_adapter: str | None,
    supports_cancel: bool,
    contract_version: int,
) -> JobContract:
    contract = JobContract(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        execution_environment_id=execution_environment_id,
        job_id=job_id,
        params_schema_ref=params_schema_ref,
        params_schema=params_schema,
        artifact_manifest=artifact_manifest,
        report_adapter=report_adapter,
        supports_cancel=supports_cancel,
        contract_version=contract_version,
    )
    session.add(contract)
    await session.flush()
    return contract


async def list_job_contracts(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    execution_environment_id: uuid.UUID,
    job_id_q: str | None = None,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[JobContract]:
    query = (
        select(JobContract)
        .where(
            JobContract.organization_id == organization_id,
            JobContract.execution_environment_id == execution_environment_id,
        )
        .order_by(JobContract.created_at.desc(), JobContract.id.desc())
    )
    if job_id_q is not None:
        query = query.where(JobContract.job_id == job_id_q)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                JobContract.created_at < cursor_created_at,
                and_(
                    JobContract.created_at == cursor_created_at,
                    JobContract.id < cursor_id,
                ),
            )
        )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_job_contract(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    execution_environment_id: uuid.UUID,
    job_id: str,
) -> JobContract | None:
    result = await session.execute(
        select(JobContract).where(
            JobContract.organization_id == organization_id,
            JobContract.execution_environment_id == execution_environment_id,
            JobContract.job_id == job_id,
        )
    )
    return result.scalar_one_or_none()
