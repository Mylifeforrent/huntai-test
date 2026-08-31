import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_org_status_expires", "organization_id", "status", "expires_at"),
        Index("ix_approval_requests_org_initiator", "organization_id", "initiator_id"),
        Index(
            "ix_approval_requests_org_target",
            "organization_id",
            "target_object_type",
            "target_object_id",
        ),
        {"schema": "approval_policy"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_object_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    param_hash: Mapped[str] = mapped_column(Text, nullable=False)
    card_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    execution_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiator_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    escalate_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expired_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    original_initiator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    snapshot_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effect_level: Mapped[str] = mapped_column(Text, nullable=False)


class CommandIdempotencyRecord(Base):
    __tablename__ = "command_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_approval_policy_idempotency_org_command_key",
        ),
        {"schema": "approval_policy"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
