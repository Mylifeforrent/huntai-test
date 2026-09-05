"""gate_evaluations

Revision ID: 0019_gate_evaluations
Revises: 0018_artifacts
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0019_gate_evaluations"
down_revision: str | None = "0018_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gate_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "policy_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column(
            "threshold_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "check_run_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("waiver_approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        schema="quality_gates",
    )
    op.create_index(
        "ix_gate_evaluations_org_run_created",
        "gate_evaluations",
        ["organization_id", "test_run_id", "created_at"],
        schema="quality_gates",
    )
    op.create_index(
        "ix_gate_evaluations_org_result",
        "gate_evaluations",
        ["organization_id", "result"],
        schema="quality_gates",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_gate_evaluations_org_result",
        table_name="gate_evaluations",
        schema="quality_gates",
    )
    op.drop_index(
        "ix_gate_evaluations_org_run_created",
        table_name="gate_evaluations",
        schema="quality_gates",
    )
    op.drop_table("gate_evaluations", schema="quality_gates")
