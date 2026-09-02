"""Append-only writes for case results and step runs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import repository as repo


@dataclass(frozen=True)
class CaseResultWrite:
    test_run_id: uuid.UUID
    test_case_id: uuid.UUID
    test_case_version_id: uuid.UUID | None
    attempt_seq: int
    outcome: str
    is_late: bool = False
    is_partial: bool = False
    chunk_key: str | None = None
    normalized_summary: dict[str, Any] | None = None
    data_classification: str = "Internal"


@dataclass(frozen=True)
class StepRunWrite:
    case_result_id: uuid.UUID
    step_index: int
    action: dict[str, Any] | None
    assertion_results: dict[str, Any] | list[dict[str, Any]] | None
    is_incomplete: bool
    observation_ref: str | None = None
    token_usage: dict[str, Any] | None = None


async def append_case_result(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    payload: CaseResultWrite,
) -> uuid.UUID:
    row = await repo.insert_case_result(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        test_run_id=payload.test_run_id,
        test_case_id=payload.test_case_id,
        test_case_version_id=payload.test_case_version_id,
        attempt_seq=payload.attempt_seq,
        outcome=payload.outcome,
        is_late=payload.is_late,
        is_partial=payload.is_partial,
        chunk_key=payload.chunk_key,
        normalized_summary=payload.normalized_summary,
        data_classification=payload.data_classification,
    )
    return row.id


async def append_step_run(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID | None,
    created_at: datetime,
    payload: StepRunWrite,
) -> uuid.UUID:
    assertion_payload: dict[str, Any] | None
    if isinstance(payload.assertion_results, list):
        assertion_payload = {"items": payload.assertion_results}
    else:
        assertion_payload = payload.assertion_results
    row = await repo.insert_step_run(
        session,
        organization_id=organization_id,
        created_at=created_at,
        created_by=created_by,
        case_result_id=payload.case_result_id,
        step_index=payload.step_index,
        action=payload.action,
        observation_ref=payload.observation_ref,
        assertion_results=assertion_payload,
        token_usage=payload.token_usage,
        is_incomplete=payload.is_incomplete,
    )
    return row.id
