"""copilot_sessions table (FR-16, S-M3-04)

Revision ID: 0025_copilot_sessions
Revises: 0024_release_orchestration
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025_copilot_sessions"
down_revision: str | None = "0024_release_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("selected_skill_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("messages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("data_classification", sa.Text(), nullable=False, server_default="Confidential"),
        schema="ai_governance",
    )
    op.create_index(
        "ix_copilot_sessions_org_user",
        "copilot_sessions",
        ["organization_id", "user_id", "updated_at"],
        schema="ai_governance",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_copilot_sessions_org_user",
        table_name="copilot_sessions",
        schema="ai_governance",
    )
    op.drop_table("copilot_sessions", schema="ai_governance")
