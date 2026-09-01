import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.run_orchestration.models import CommandIdempotencyRecord, TestRun

WAITING_STATUSES = frozenset({"WAITING_APPROVAL", "WAITING_EXTERNAL"})
ACTIVE_RECLAIM_STATUSES = frozenset({"RUNNING", "STOPPING"})


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


async def get_test_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_run_id: uuid.UUID,
    for_update: bool = False,
) -> TestRun | None:
    query = select(TestRun).where(
        TestRun.organization_id == organization_id,
        TestRun.id == test_run_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_test_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID,
    project_id: uuid.UUID,
    plan_id: uuid.UUID | None,
    env_id: uuid.UUID,
    execution_source: str,
    trigger_type: str,
    idempotency_key: str,
    status: str,
    snapshot: dict[str, Any],
) -> TestRun:
    run = TestRun(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        project_id=project_id,
        plan_id=plan_id,
        env_id=env_id,
        execution_source=execution_source,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        status=status,
        gate_evaluation_id=None,
        snapshot=snapshot,
        last_heartbeat_at=None,
        stop_signal_at=None,
        result_summary=None,
    )
    session.add(run)
    await session.flush()
    return run


async def update_test_run_cancel(
    session: AsyncSession,
    *,
    run: TestRun,
    new_status: str,
    updated_at: datetime,
    stop_signal_at: datetime,
) -> TestRun:
    run.status = new_status
    run.updated_at = updated_at
    run.stop_signal_at = stop_signal_at
    run.aggregate_version += 1
    await session.flush()
    return run


async def list_test_runs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    status: str | None = None,
    execution_source: str | None = None,
    trigger_type: str | None = None,
    plan_id: uuid.UUID | None = None,
    env_id: uuid.UUID | None = None,
    include_waiting: bool = True,
    sort_desc: bool = True,
    cursor_created_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[TestRun]:
    if sort_desc:
        order_cols = (TestRun.created_at.desc(), TestRun.id.desc())
    else:
        order_cols = (TestRun.created_at.asc(), TestRun.id.asc())

    query = (
        select(TestRun)
        .where(
            TestRun.organization_id == organization_id,
            TestRun.project_id == project_id,
        )
        .order_by(*order_cols)
    )
    if status is not None:
        query = query.where(TestRun.status == status)
    if execution_source is not None:
        query = query.where(TestRun.execution_source == execution_source)
    if trigger_type is not None:
        query = query.where(TestRun.trigger_type == trigger_type)
    if plan_id is not None:
        query = query.where(TestRun.plan_id == plan_id)
    if env_id is not None:
        query = query.where(TestRun.env_id == env_id)
    if not include_waiting:
        query = query.where(TestRun.status.notin_(tuple(WAITING_STATUSES)))

    if cursor_created_at is not None and cursor_id is not None:
        if sort_desc:
            query = query.where(
                or_(
                    TestRun.created_at < cursor_created_at,
                    and_(
                        TestRun.created_at == cursor_created_at,
                        TestRun.id < cursor_id,
                    ),
                )
            )
        else:
            query = query.where(
                or_(
                    TestRun.created_at > cursor_created_at,
                    and_(
                        TestRun.created_at == cursor_created_at,
                        TestRun.id > cursor_id,
                    ),
                )
            )

    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def reclaim_stale_active_runs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    now: datetime,
    heartbeat_timeout_seconds: int,
) -> int:
    from datetime import timedelta

    cutoff = now - timedelta(seconds=heartbeat_timeout_seconds)
    query = (
        select(TestRun)
        .where(
            TestRun.status.in_(tuple(ACTIVE_RECLAIM_STATUSES)),
            or_(
                TestRun.last_heartbeat_at.is_(None),
                TestRun.last_heartbeat_at < cutoff,
            ),
        )
        .with_for_update()
    )
    if organization_id is not None:
        query = query.where(TestRun.organization_id == organization_id)
    result = await session.execute(query)
    rows = list(result.scalars().all())
    for run in rows:
        run.status = "TIMEOUT"
        run.updated_at = now
        run.aggregate_version += 1
    if rows:
        await session.flush()
    return len(rows)
