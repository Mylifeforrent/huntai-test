"""artifacts: export-package receipt linkage (S-M2-06)

Revision ID: 0022_artifact_export_receipt
Revises: 0021_case_result_chunk_unique
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_artifact_export_receipt"
down_revision: str | None = "0021_case_result_chunk_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "artifacts",
        "test_run_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema="results_evidence",
    )
    op.add_column(
        "artifacts",
        sa.Column(
            "source_receipt_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="results_evidence",
    )
    op.create_index(
        "ix_artifacts_org_source_receipt",
        "artifacts",
        ["organization_id", "source_receipt_id"],
        unique=False,
        schema="results_evidence",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_artifacts_org_source_receipt",
        table_name="artifacts",
        schema="results_evidence",
    )
    op.drop_column(
        "artifacts",
        "source_receipt_id",
        schema="results_evidence",
    )
    op.alter_column(
        "artifacts",
        "test_run_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema="results_evidence",
    )
