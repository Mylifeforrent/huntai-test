import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ExecutionEnvironment(Base):
    __tablename__ = "execution_environments"
    __table_args__ = (
        Index("ix_execution_environments_org_status", "organization_id", "status"),
        Index("ix_execution_environments_org_env_type", "organization_id", "env_type"),
        {"schema": "execution_registry"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    env_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    health_status: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    capacity: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    scope_level: Mapped[str] = mapped_column(Text, nullable=False)
    standing_auth_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class JobContract(Base):
    __tablename__ = "job_contracts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "execution_environment_id",
            "job_id",
            name="uq_job_contracts_org_env_job",
        ),
        {"schema": "execution_registry"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_environment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    job_id: Mapped[str] = mapped_column(Text, nullable=False)
    params_schema_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    artifact_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    report_adapter: Mapped[str | None] = mapped_column(Text, nullable=True)
    supports_cancel: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_execution_registry_idempotency_org_command_key",
        ),
        {"schema": "execution_registry"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
