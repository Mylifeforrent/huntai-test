"""run_orchestration schema for TestRun queue

Revision ID: 0008_run_orchestration
Revises: 0007_execution_registry
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_run_orchestration"
down_revision: str | None = "0007_execution_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS run_orchestration")

    op.create_table(
        "test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("env_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_source", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("gate_evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_signal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_test_runs_org_idempotency_key",
        ),
        schema="run_orchestration",
    )
    op.create_index(
        "ix_test_runs_org_status_created",
        "test_runs",
        ["organization_id", "status", "created_at"],
        schema="run_orchestration",
    )
    op.create_index(
        "ix_test_runs_org_project_created",
        "test_runs",
        ["organization_id", "project_id", "created_at"],
        schema="run_orchestration",
    )
    op.create_index(
        "ix_test_runs_org_env",
        "test_runs",
        ["organization_id", "env_id"],
        schema="run_orchestration",
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
            name="uq_run_orchestration_idempotency_org_command_key",
        ),
        schema="run_orchestration",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="run_orchestration")
    op.drop_index(
        "ix_test_runs_org_env",
        table_name="test_runs",
        schema="run_orchestration",
    )
    op.drop_index(
        "ix_test_runs_org_project_created",
        table_name="test_runs",
        schema="run_orchestration",
    )
    op.drop_index(
        "ix_test_runs_org_status_created",
        table_name="test_runs",
        schema="run_orchestration",
    )
    op.drop_table("test_runs", schema="run_orchestration")
    op.execute("DROP SCHEMA IF EXISTS run_orchestration")
