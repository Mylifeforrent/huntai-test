"""execution_registry schema for execution environments and job contracts

Revision ID: 0007_execution_registry
Revises: 0006_siem_export
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_execution_registry"
down_revision: str | None = "0006_siem_export"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS execution_registry")

    op.create_table(
        "execution_environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("env_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("credential_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("health_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("capacity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scope_level", sa.Text(), nullable=False),
        sa.Column("standing_auth_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="execution_registry",
    )
    op.create_index(
        "ix_execution_environments_org_status",
        "execution_environments",
        ["organization_id", "status"],
        schema="execution_registry",
    )
    op.create_index(
        "ix_execution_environments_org_env_type",
        "execution_environments",
        ["organization_id", "env_type"],
        schema="execution_registry",
    )

    op.create_table(
        "job_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("execution_environment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("params_schema_ref", sa.Text(), nullable=True),
        sa.Column("params_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report_adapter", sa.Text(), nullable=True),
        sa.Column("supports_cancel", sa.Boolean(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "execution_environment_id",
            "job_id",
            name="uq_job_contracts_org_env_job",
        ),
        schema="execution_registry",
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
            name="uq_execution_registry_idempotency_org_command_key",
        ),
        schema="execution_registry",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="execution_registry")
    op.drop_table("job_contracts", schema="execution_registry")
    op.drop_index(
        "ix_execution_environments_org_env_type",
        table_name="execution_environments",
        schema="execution_registry",
    )
    op.drop_index(
        "ix_execution_environments_org_status",
        table_name="execution_environments",
        schema="execution_registry",
    )
    op.drop_table("execution_environments", schema="execution_registry")
    op.execute("DROP SCHEMA IF EXISTS execution_registry")
