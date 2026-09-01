"""quota_governance schema for org_quotas ledger

Revision ID: 0005_quota_governance
Revises: 0004_ai_governance
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_quota_governance"
down_revision: str | None = "0004_ai_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quota_governance")

    op.create_table(
        "org_quotas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("token_budget", sa.Numeric(), nullable=False),
        sa.Column("token_reserved", sa.Numeric(), nullable=False),
        sa.Column("token_consumed", sa.Numeric(), nullable=False),
        sa.Column("executor_slot_quota", sa.Integer(), nullable=False),
        sa.Column("perf_concurrency_quota", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_org_quotas_organization_id"),
        schema="quota_governance",
    )


def downgrade() -> None:
    op.drop_table("org_quotas", schema="quota_governance")
    op.execute("DROP SCHEMA IF EXISTS quota_governance")
