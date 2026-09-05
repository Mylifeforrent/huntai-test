import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.test_assets.models import (
    CommandIdempotencyRecord,
    ImportSource,
    TestCase,
    TestCaseVersion,
    TestPlan,
    TestPlanCase,
)


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def encode_updated_id_cursor(*, updated_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": updated_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_updated_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        updated_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return updated_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


def encode_version_seq_cursor(*, version_seq: int, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"s": version_seq, "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_version_seq_cursor(cursor: str) -> tuple[int, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        version_seq = int(data["s"])
        item_id = uuid.UUID(data["i"])
        return version_seq, item_id
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


async def get_test_case(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
    for_update: bool = False,
) -> TestCase | None:
    query = select(TestCase).where(
        TestCase.organization_id == organization_id,
        TestCase.id == test_case_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_test_case_version(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    version_id: uuid.UUID,
) -> TestCaseVersion | None:
    result = await session.execute(
        select(TestCaseVersion).where(
            TestCaseVersion.organization_id == organization_id,
            TestCaseVersion.id == version_id,
        )
    )
    return result.scalar_one_or_none()


async def list_test_cases(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    lifecycle_status: str | None = None,
    validity: str | None = None,
    tags: str | None = None,
    case_type: str | None = None,
    execution_mode: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    cursor_updated_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int,
) -> list[TestCase]:
    query = (
        select(TestCase)
        .where(
            TestCase.organization_id == organization_id,
            TestCase.project_id == project_id,
        )
        .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
    )
    if lifecycle_status is not None:
        query = query.where(TestCase.lifecycle_status == lifecycle_status)
    if validity is not None:
        query = query.where(TestCase.validity == validity)
    if tags is not None:
        query = query.where(TestCase.tags.contains([tags]))
    if case_type is not None:
        query = query.where(TestCase.case_type == case_type)
    if execution_mode is not None:
        query = query.where(TestCase.execution_mode == execution_mode)
    if priority is not None:
        query = query.where(TestCase.priority == priority)
    if q is not None:
        query = query.where(TestCase.title.ilike(f"%{q}%"))
    if cursor_updated_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                TestCase.updated_at < cursor_updated_at,
                and_(TestCase.updated_at == cursor_updated_at, TestCase.id < cursor_id),
            )
        )
    query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def insert_test_case(session: AsyncSession, row: TestCase) -> TestCase:
    session.add(row)
    await session.flush()
    return row


async def insert_test_case_version(session: AsyncSession, row: TestCaseVersion) -> TestCaseVersion:
    session.add(row)
    await session.flush()
    return row


async def list_test_case_versions(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
    cursor_version_seq: int | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int,
) -> list[TestCaseVersion]:
    query = (
        select(TestCaseVersion)
        .where(
            TestCaseVersion.organization_id == organization_id,
            TestCaseVersion.test_case_id == test_case_id,
        )
        .order_by(TestCaseVersion.version_seq.desc(), TestCaseVersion.id.desc())
    )
    if cursor_version_seq is not None and cursor_id is not None:
        query = query.where(
            or_(
                TestCaseVersion.version_seq < cursor_version_seq,
                and_(
                    TestCaseVersion.version_seq == cursor_version_seq,
                    TestCaseVersion.id < cursor_id,
                ),
            )
        )
    query = query.limit(limit + 1)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_test_case_version_for_case(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_case_id: uuid.UUID,
    version_id: uuid.UUID,
) -> TestCaseVersion | None:
    result = await session.execute(
        select(TestCaseVersion).where(
            TestCaseVersion.organization_id == organization_id,
            TestCaseVersion.test_case_id == test_case_id,
            TestCaseVersion.id == version_id,
        )
    )
    return result.scalar_one_or_none()


async def get_import_source(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    source_id: uuid.UUID,
) -> ImportSource | None:
    result = await session.execute(
        select(ImportSource).where(
            ImportSource.organization_id == organization_id,
            ImportSource.id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def insert_import_source(session: AsyncSession, row: ImportSource) -> ImportSource:
    session.add(row)
    await session.flush()
    return row


async def count_test_cases_for_project(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> int:
    result = await session.execute(
        select(TestCase.id).where(
            TestCase.organization_id == organization_id,
            TestCase.project_id == project_id,
        )
    )
    return len(list(result.scalars().all()))


async def get_test_plan(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_plan_id: uuid.UUID,
    for_update: bool = False,
) -> TestPlan | None:
    query = select(TestPlan).where(
        TestPlan.organization_id == organization_id,
        TestPlan.id == test_plan_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_test_plans(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    q: str | None = None,
    cursor_updated_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
    limit: int,
) -> list[tuple[TestPlan, int]]:
    case_count_subq = (
        select(
            TestPlanCase.test_plan_id.label("plan_id"),
            func.count(TestPlanCase.id).label("case_count"),
        )
        .where(TestPlanCase.organization_id == organization_id)
        .group_by(TestPlanCase.test_plan_id)
        .subquery()
    )
    query = (
        select(
            TestPlan,
            func.coalesce(case_count_subq.c.case_count, 0).label("case_count"),
        )
        .outerjoin(case_count_subq, TestPlan.id == case_count_subq.c.plan_id)
        .where(
            TestPlan.organization_id == organization_id,
            TestPlan.project_id == project_id,
        )
        .order_by(TestPlan.updated_at.desc(), TestPlan.id.desc())
    )
    if q is not None:
        query = query.where(TestPlan.name.ilike(f"%{q}%"))
    if cursor_updated_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                TestPlan.updated_at < cursor_updated_at,
                and_(TestPlan.updated_at == cursor_updated_at, TestPlan.id < cursor_id),
            )
        )
    query = query.limit(limit + 1)
    result = await session.execute(query)
    return [(row[0], int(row[1])) for row in result.all()]


async def insert_test_plan(session: AsyncSession, row: TestPlan) -> TestPlan:
    session.add(row)
    await session.flush()
    return row


async def list_plan_case_ids(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_plan_id: uuid.UUID,
) -> list[uuid.UUID]:
    result = await session.execute(
        select(TestPlanCase.test_case_id)
        .where(
            TestPlanCase.organization_id == organization_id,
            TestPlanCase.test_plan_id == test_plan_id,
        )
        .order_by(TestPlanCase.created_at.asc(), TestPlanCase.id.asc())
    )
    return list(result.scalars().all())


async def replace_plan_cases(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    test_plan_id: uuid.UUID,
    case_ids: list[uuid.UUID],
    created_by: uuid.UUID | None,
    created_at: datetime,
) -> None:
    await session.execute(
        delete(TestPlanCase).where(
            TestPlanCase.organization_id == organization_id,
            TestPlanCase.test_plan_id == test_plan_id,
        )
    )
    for case_id in case_ids:
        session.add(
            TestPlanCase(
                id=uuid.uuid4(),
                organization_id=organization_id,
                created_at=created_at,
                created_by=created_by,
                test_plan_id=test_plan_id,
                test_case_id=case_id,
            )
        )
    await session.flush()
