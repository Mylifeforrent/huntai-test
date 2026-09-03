"""ai_governance schema for model routes and invocation logs

Revision ID: 0004_ai_governance
Revises: 0003_action_previews
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_ai_governance"
down_revision: str | None = "0003_action_previews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ai_governance")

    op.create_table(
        "model_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("provider_allowlist", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("max_cost", sa.Numeric(), nullable=False),
        sa.Column("fallback", postgresql.JSONB(), nullable=True),
        sa.Column("require_prompt_version", sa.Boolean(), nullable=False),
        sa.Column("require_structured_output", sa.Boolean(), nullable=False),
        sa.Column("credential_ref", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "task_type",
            "data_classification",
            name="uq_model_routes_org_task_classification",
        ),
        schema="ai_governance",
    )

    op.create_table(
        "ai_invocation_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("cost", sa.Numeric(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("skill_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_route_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("copilot_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_ref", sa.Text(), nullable=True),
        schema="ai_governance",
    )
    op.create_index(
        "ix_ai_invocation_logs_org_created",
        "ai_invocation_logs",
        ["organization_id", "created_at"],
        unique=False,
        schema="ai_governance",
    )
    op.create_index(
        "ix_ai_invocation_logs_org_user_created",
        "ai_invocation_logs",
        ["organization_id", "user_id", "created_at"],
        unique=False,
        schema="ai_governance",
    )
    op.create_index(
        "ix_ai_invocation_logs_org_copilot",
        "ai_invocation_logs",
        ["organization_id", "copilot_session_id"],
        unique=False,
        schema="ai_governance",
        postgresql_where=sa.text("copilot_session_id IS NOT NULL"),
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
            name="uq_ai_governance_idempotency_org_command_key",
        ),
        schema="ai_governance",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="ai_governance")
    op.drop_index(
        "ix_ai_invocation_logs_org_copilot",
        table_name="ai_invocation_logs",
        schema="ai_governance",
    )
    op.drop_index(
        "ix_ai_invocation_logs_org_user_created",
        table_name="ai_invocation_logs",
        schema="ai_governance",
    )
    op.drop_index(
        "ix_ai_invocation_logs_org_created",
        table_name="ai_invocation_logs",
        schema="ai_governance",
    )
    op.drop_table("ai_invocation_logs", schema="ai_governance")
    op.drop_table("model_routes", schema="ai_governance")
    op.execute("DROP SCHEMA IF EXISTS ai_governance")
