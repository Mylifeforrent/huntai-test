"""action_previews table and approval binding columns

Revision ID: 0003_action_previews
Revises: 0002_approval_policy
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_action_previews"
down_revision: str | None = "0002_approval_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="approval_policy",
    )
    op.add_column(
        "approval_requests",
        sa.Column("expected_target_version", sa.Integer(), nullable=True),
        schema="approval_policy",
    )

    op.create_table(
        "action_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preview_payload", postgresql.JSONB(), nullable=False),
        schema="approval_policy",
    )
    op.create_index(
        "ix_action_previews_org_expires",
        "action_previews",
        ["organization_id", "expires_at"],
        unique=False,
        schema="approval_policy",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_action_previews_org_expires",
        table_name="action_previews",
        schema="approval_policy",
    )
    op.drop_table("action_previews", schema="approval_policy")
    op.drop_column("approval_requests", "expected_target_version", schema="approval_policy")
    op.drop_column("approval_requests", "project_id", schema="approval_policy")
