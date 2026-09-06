"""ReleaseTask domain models (FR-15, S-M3-03; schema release_orchestration)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReleaseTask(Base):
    __tablename__ = "release_tasks"
    __table_args__ = (
        Index("ix_release_tasks_org_project", "organization_id", "project_id"),
        {"schema": "release_orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jira_version_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    notes_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    a5: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    gate_result_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    divergence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prepare_idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReleaseItemRef(Base):
    __tablename__ = "release_item_refs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "prepare_key",
            name="uq_release_item_refs_org_prepare_key",
        ),
        {"schema": "release_orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    release_task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_system: Mapped[str] = mapped_column(Text, nullable=False)
    external_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    prepare_key: Mapped[str] = mapped_column(Text, nullable=False)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_release_orchestration_idempotency_org_command_key",
        ),
        {"schema": "release_orchestration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
