import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CaseResult(Base):
    __tablename__ = "case_results"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "test_run_id",
            "test_case_id",
            "attempt_seq",
            name="uq_case_results_org_run_case_attempt",
        ),
        Index("ix_case_results_org_test_run", "organization_id", "test_run_id"),
        {"schema": "results_evidence"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    test_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    attempt_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    is_late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chunk_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)


class StepRun(Base):
    __tablename__ = "step_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "case_result_id",
            "step_index",
            name="uq_step_runs_org_case_result_step",
        ),
        {"schema": "results_evidence"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    case_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    observation_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    assertion_results: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_incomplete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FailureCluster(Base):
    __tablename__ = "failure_clusters"
    __table_args__ = (
        Index("ix_failure_clusters_org_test_run", "organization_id", "test_run_id"),
        {"schema": "results_evidence"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    test_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    blocking_judgment: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    failure_refs: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    correction_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    unclustered_refs: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    fixes: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
