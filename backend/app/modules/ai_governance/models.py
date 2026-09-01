import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ModelRoute(Base):
    __tablename__ = "model_routes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "task_type",
            "data_classification",
            name="uq_model_routes_org_task_classification",
        ),
        {"schema": "ai_governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)
    provider_allowlist: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    max_cost: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    fallback: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    require_prompt_version: Mapped[bool] = mapped_column(nullable=False)
    require_structured_output: Mapped[bool] = mapped_column(nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)


class AIInvocationLog(Base):
    __tablename__ = "ai_invocation_logs"
    __table_args__ = (
        Index("ix_ai_invocation_logs_org_created", "organization_id", "created_at"),
        Index(
            "ix_ai_invocation_logs_org_user_created",
            "organization_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_ai_invocation_logs_org_copilot",
            "organization_id",
            "copilot_session_id",
            postgresql_where="copilot_session_id IS NOT NULL",
        ),
        {"schema": "ai_governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    skill_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_route_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    copilot_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_ai_governance_idempotency_org_command_key",
        ),
        {"schema": "ai_governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
