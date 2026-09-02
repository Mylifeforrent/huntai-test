"""run_orchestration command_receipts + results_evidence case_results/step_runs

Revision ID: 0013_run_results_receipts
Revises: 0012_a1_generations
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_run_results_receipts"
down_revision: str | None = "0012_a1_generations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "command_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        schema="run_orchestration",
    )
    op.create_index(
        "ix_command_receipts_org_resource",
        "command_receipts",
        ["organization_id", "resource_id"],
        schema="run_orchestration",
    )

    op.create_table(
        "case_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_seq", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("chunk_key", sa.Text(), nullable=True),
        sa.Column("normalized_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "test_run_id",
            "test_case_id",
            "attempt_seq",
            name="uq_case_results_org_run_case_attempt",
        ),
        schema="results_evidence",
    )
    op.create_index(
        "ix_case_results_org_test_run",
        "case_results",
        ["organization_id", "test_run_id"],
        schema="results_evidence",
    )
    op.create_index(
        "ix_case_results_org_run_chunk_key",
        "case_results",
        ["organization_id", "test_run_id", "chunk_key"],
        unique=True,
        schema="results_evidence",
        postgresql_where=sa.text("chunk_key IS NOT NULL"),
    )

    op.create_table(
        "step_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("case_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("observation_ref", sa.Text(), nullable=True),
        sa.Column("assertion_results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_incomplete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint(
            "organization_id",
            "case_result_id",
            "step_index",
            name="uq_step_runs_org_case_result_step",
        ),
        schema="results_evidence",
    )


def downgrade() -> None:
    op.drop_table("step_runs", schema="results_evidence")
    op.drop_index(
        "ix_case_results_org_run_chunk_key",
        table_name="case_results",
        schema="results_evidence",
    )
    op.drop_index(
        "ix_case_results_org_test_run",
        table_name="case_results",
        schema="results_evidence",
    )
    op.drop_table("case_results", schema="results_evidence")
    op.drop_index(
        "ix_command_receipts_org_resource",
        table_name="command_receipts",
        schema="run_orchestration",
    )
    op.drop_table("command_receipts", schema="run_orchestration")
