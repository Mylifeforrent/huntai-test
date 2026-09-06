import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = (
        Index(
            "ix_test_cases_org_project_lifecycle",
            "organization_id",
            "project_id",
            "lifecycle_status",
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    case_type: Mapped[str] = mapped_column(Text, nullable=False)
    execution_mode: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(Text, nullable=False)
    validity: Mapped[str] = mapped_column(Text, nullable=False)
    invalid_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    script_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_binding: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    jira_story_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class TestCaseVersion(Base):
    __tablename__ = "test_case_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "test_case_id",
            "version_seq",
            name="uq_test_case_versions_org_case_seq",
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    test_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)


class ImportSource(Base):
    __tablename__ = "import_sources"
    __table_args__ = ({"schema": "test_assets"},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)


class TestPlan(Base):
    __tablename__ = "test_plans"
    __table_args__ = (
        Index(
            "ix_test_plans_org_project",
            "organization_id",
            "project_id",
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    jira_fix_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_binding: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class TestPlanCase(Base):
    __tablename__ = "test_plan_cases"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "test_plan_id",
            "test_case_id",
            name="uq_test_plan_cases_org_plan_case",
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    test_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_test_assets_idempotency_org_command_key",
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class PerfBaseline(Base):
    __tablename__ = "perf_baselines"
    __table_args__ = (
        Index("ix_perf_baselines_org_scenario", "organization_id", "scenario_test_case_id"),
        Index(
            "uq_perf_baselines_active_scenario",
            "organization_id",
            "scenario_test_case_id",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
        {"schema": "test_assets"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario_test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_assets.test_cases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tolerance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    latest_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
