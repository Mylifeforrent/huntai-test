"""quality_gate_policies

Revision ID: 0017_quality_gate_policies
Revises: 0016_test_plans
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_quality_gate_policies"
down_revision: str | None = "0016_test_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS quality_gates")

    op.create_table(
        "quality_gate_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "thresholds",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        schema="quality_gates",
    )
    op.create_index(
        "ix_quality_gate_policies_org_project",
        "quality_gate_policies",
        ["organization_id", "project_id"],
        schema="quality_gates",
    )

    op.create_table(
        "command_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_quality_gates_idempotency_org_command_key",
        ),
        schema="quality_gates",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="quality_gates")
    op.drop_index(
        "ix_quality_gate_policies_org_project",
        table_name="quality_gate_policies",
        schema="quality_gates",
    )
    op.drop_table("quality_gate_policies", schema="quality_gates")
    op.execute("DROP SCHEMA IF EXISTS quality_gates CASCADE")
