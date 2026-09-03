"""test_assets schema for TestCase and import sources

Revision ID: 0011_test_assets
Revises: 0010_api_tokens
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_test_assets"
down_revision: str | None = "0010_api_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS test_assets")

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.Text(), nullable=False),
        sa.Column("execution_mode", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("lifecycle_status", sa.Text(), nullable=False),
        sa.Column("validity", sa.Text(), nullable=False),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("script_ref", sa.Text(), nullable=True),
        sa.Column("job_binding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("jira_story_key", sa.Text(), nullable=True),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="test_assets",
    )
    op.create_index(
        "ix_test_cases_org_project_lifecycle",
        "test_cases",
        ["organization_id", "project_id", "lifecycle_status"],
        schema="test_assets",
    )

    op.create_table(
        "test_case_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_seq", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "test_case_id",
            "version_seq",
            name="uq_test_case_versions_org_case_seq",
        ),
        schema="test_assets",
    )

    op.create_table(
        "import_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        schema="test_assets",
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
            name="uq_test_assets_idempotency_org_command_key",
        ),
        schema="test_assets",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="test_assets")
    op.drop_table("import_sources", schema="test_assets")
    op.drop_table("test_case_versions", schema="test_assets")
    op.drop_index(
        "ix_test_cases_org_project_lifecycle",
        table_name="test_cases",
        schema="test_assets",
    )
    op.drop_table("test_cases", schema="test_assets")
    op.execute("DROP SCHEMA IF EXISTS test_assets CASCADE")
