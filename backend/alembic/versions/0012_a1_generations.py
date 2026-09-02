"""ai_governance.a1_generations staging table

Revision ID: 0012_a1_generations
Revises: 0011_test_assets
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_a1_generations"
down_revision: str | None = "0011_test_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "a1_generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("import_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inline_content", sa.Text(), nullable=True),
        sa.Column("drafts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("failed_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("invocation_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="ai_governance",
    )
    op.create_index(
        "ix_a1_generations_org_project_status",
        "a1_generations",
        ["organization_id", "project_id", "status"],
        schema="ai_governance",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_a1_generations_org_project_status",
        table_name="a1_generations",
        schema="ai_governance",
    )
    op.drop_table("a1_generations", schema="ai_governance")
