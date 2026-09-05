"""artifacts table for Playwright evidence

Revision ID: 0018_artifacts
Revises: 0017_quality_gate_policies
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_artifacts"
down_revision: str | None = "0017_quality_gate_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("case_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        schema="results_evidence",
    )
    op.create_index(
        "ix_artifacts_org_object_key",
        "artifacts",
        ["organization_id", "object_key"],
        unique=True,
        schema="results_evidence",
    )
    op.create_index(
        "ix_artifacts_org_test_run",
        "artifacts",
        ["organization_id", "test_run_id"],
        schema="results_evidence",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_artifacts_org_test_run",
        table_name="artifacts",
        schema="results_evidence",
    )
    op.drop_index(
        "ix_artifacts_org_object_key",
        table_name="artifacts",
        schema="results_evidence",
    )
    op.drop_table("artifacts", schema="results_evidence")
