import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Connector(Base):
    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "type",
            "name",
            name="uq_connectors_org_type_name",
        ),
        Index("ix_connectors_org_type", "organization_id", "type"),
        {"schema": "integration_hub"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    auth_method: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str] = mapped_column(Text, nullable=False)
    action_contract: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    outbound_write_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    webhook_secret_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    standing_auth_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    health_status: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ExternalObservation(Base):
    __tablename__ = "external_observations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source",
            "observation_key",
            name="uq_external_observations_org_source_key",
        ),
        Index(
            "ix_external_observations_org_connector_observed",
            "organization_id",
            "connector_id",
            "observed_at",
        ),
        {"schema": "integration_hub"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    connector_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    observation_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_classification: Mapped[str] = mapped_column(Text, nullable=False)


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "consumer_name",
            "event_id",
            name="uq_inbox_events_org_consumer_event",
        ),
        {"schema": "integration_hub"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    consumer_name: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_integration_hub_idempotency_org_command_key",
        ),
        {"schema": "integration_hub"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
