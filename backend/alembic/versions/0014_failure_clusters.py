"""failure_clusters table for A2 triage

Revision ID: 0014_failure_clusters
Revises: 0013_run_results_receipts
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_failure_clusters"
down_revision: str | None = "0013_run_results_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "failure_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("blocking_judgment", sa.Text(), nullable=False),
        sa.Column("evidence_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("failure_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column(
            "correction_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "unclustered_refs",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
        sa.Column("fixes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="results_evidence",
    )
    op.create_index(
        "ix_failure_clusters_org_test_run",
        "failure_clusters",
        ["organization_id", "test_run_id"],
        schema="results_evidence",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_failure_clusters_org_test_run",
        table_name="failure_clusters",
        schema="results_evidence",
    )
    op.drop_table("failure_clusters", schema="results_evidence")
