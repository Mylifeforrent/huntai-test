"""release_orchestration schema: release_tasks and release_item_refs (S-M3-03)

Revision ID: 0024_release_orchestration
Revises: 0023_perf_baselines
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0024_release_orchestration"
down_revision: str | None = "0023_perf_baselines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS release_orchestration")
    op.create_table(
        "release_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jira_version_ref", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("scope_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("notes_draft", sa.Text(), nullable=True),
        sa.Column("a5", postgresql.JSONB(), nullable=True),
        sa.Column("gate_result_ref", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("divergence", postgresql.JSONB(), nullable=True),
        sa.Column("prepare_idempotency_key", sa.Text(), nullable=True),
        schema="release_orchestration",
    )
    op.create_index(
        "ix_release_tasks_org_project",
        "release_tasks",
        ["organization_id", "project_id"],
        schema="release_orchestration",
    )
    op.create_table(
        "release_item_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_system", sa.Text(), nullable=False),
        sa.Column("external_item_id", sa.Text(), nullable=False),
        sa.Column("prepare_key", sa.Text(), nullable=False),
        schema="release_orchestration",
    )
    op.create_index(
        "uq_release_item_refs_prepare_key",
        "release_item_refs",
        ["organization_id", "prepare_key"],
        unique=True,
        schema="release_orchestration",
    )
    op.create_table(
        "command_idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("command_type", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_ref", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "command_type",
            "idempotency_key",
            name="uq_release_orchestration_idempotency_org_command_key",
        ),
        schema="release_orchestration",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="release_orchestration")
    op.drop_index(
        "uq_release_item_refs_prepare_key",
        table_name="release_item_refs",
        schema="release_orchestration",
    )
    op.drop_table("release_item_refs", schema="release_orchestration")
    op.drop_index(
        "ix_release_tasks_org_project",
        table_name="release_tasks",
        schema="release_orchestration",
    )
    op.drop_table("release_tasks", schema="release_orchestration")
    op.execute("DROP SCHEMA IF EXISTS release_orchestration")
