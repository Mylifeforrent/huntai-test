import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        Index("ix_test_runs_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_test_runs_org_project_created", "organization_id", "project_id", "created_at"),
        Index("ix_test_runs_org_env", "organization_id", "env_id"),
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_test_runs_org_idempotency_key",
        ),
        {"schema": "run_orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    env_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    execution_source: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    gate_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stop_signal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_run_orchestration_idempotency_org_command_key",
        ),
        {"schema": "run_orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
