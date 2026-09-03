"""evidence_objects and command_idempotency_records

Revision ID: 0015_evidence_objects
Revises: 0014_failure_clusters
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_evidence_objects"
down_revision: str | None = "0014_failure_clusters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column(
            "source_object",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("content_ref", sa.Text(), nullable=True),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        schema="results_evidence",
    )
    op.create_index(
        "ix_evidence_objects_org_subject",
        "evidence_objects",
        ["organization_id", "subject_type", "subject_id"],
        schema="results_evidence",
    )
    op.create_index(
        "ix_evidence_objects_org_created_at",
        "evidence_objects",
        ["organization_id", "created_at"],
        schema="results_evidence",
    )
    op.create_table(
        "command_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column(
            "response_ref",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_results_evidence_idempotency_org_command_key",
        ),
        schema="results_evidence",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="results_evidence")
    op.drop_index(
        "ix_evidence_objects_org_created_at",
        table_name="evidence_objects",
        schema="results_evidence",
    )
    op.drop_index(
        "ix_evidence_objects_org_subject",
        table_name="evidence_objects",
        schema="results_evidence",
    )
    op.drop_table("evidence_objects", schema="results_evidence")
