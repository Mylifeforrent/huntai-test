"""integration_hub schema for connectors and inbound webhooks

Revision ID: 0009_integration_hub
Revises: 0008_run_orchestration
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_integration_hub"
down_revision: str | None = "0008_run_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS integration_hub")

    op.create_table(
        "connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("auth_method", sa.Text(), nullable=False),
        sa.Column("credential_ref", sa.Text(), nullable=False),
        sa.Column("action_contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outbound_write_enabled", sa.Boolean(), nullable=False),
        sa.Column("webhook_secret_ref", sa.Text(), nullable=True),
        sa.Column("standing_auth_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("health_status", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "type",
            "name",
            name="uq_connectors_org_type_name",
        ),
        schema="integration_hub",
    )
    op.create_index(
        "ix_connectors_org_type",
        "connectors",
        ["organization_id", "type"],
        schema="integration_hub",
    )

    op.create_table(
        "external_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_key", sa.Text(), nullable=False),
        sa.Column("payload_ref", sa.Text(), nullable=True),
        sa.Column("signature_ok", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "organization_id",
            "source",
            "observation_key",
            name="uq_external_observations_org_source_key",
        ),
        schema="integration_hub",
    )
    op.create_index(
        "ix_external_observations_org_connector_observed",
        "external_observations",
        ["organization_id", "connector_id", "observed_at"],
        schema="integration_hub",
    )

    op.create_table(
        "inbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("consumer_name", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "consumer_name",
            "event_id",
            name="uq_inbox_events_org_consumer_event",
        ),
        schema="integration_hub",
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
            name="uq_integration_hub_idempotency_org_command_key",
        ),
        schema="integration_hub",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="integration_hub")
    op.drop_table("inbox_events", schema="integration_hub")
    op.drop_index(
        "ix_external_observations_org_connector_observed",
        table_name="external_observations",
        schema="integration_hub",
    )
    op.drop_table("external_observations", schema="integration_hub")
    op.drop_index(
        "ix_connectors_org_type",
        table_name="connectors",
        schema="integration_hub",
    )
    op.drop_table("connectors", schema="integration_hub")
    op.execute("DROP SCHEMA IF EXISTS integration_hub")
