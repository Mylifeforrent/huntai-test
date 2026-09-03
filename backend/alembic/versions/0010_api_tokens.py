"""integration_hub api_tokens table

Revision ID: 0010_api_tokens
Revises: 0009_integration_hub
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_api_tokens"
down_revision: str | None = "0009_integration_hub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("issued_to_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_prefix", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("project_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "token_hash",
            name="uq_api_tokens_org_token_hash",
        ),
        schema="integration_hub",
    )
    op.create_index(
        "ix_api_tokens_org_issued_to_user",
        "api_tokens",
        ["organization_id", "issued_to_user_id"],
        schema="integration_hub",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_api_tokens_org_issued_to_user",
        table_name="api_tokens",
        schema="integration_hub",
    )
    op.drop_table("api_tokens", schema="integration_hub")
