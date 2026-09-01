import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrgQuota(Base):
    __tablename__ = "org_quotas"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_quotas_organization_id"),
        {"schema": "quota_governance"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    token_budget: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    token_reserved: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    token_consumed: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    executor_slot_quota: Mapped[int] = mapped_column(Integer, nullable=False)
    perf_concurrency_quota: Mapped[int] = mapped_column(Integer, nullable=False)
