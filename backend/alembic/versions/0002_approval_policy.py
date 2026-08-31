"""approval_policy schema for M0 action previews

Revision ID: 0002_approval_policy
Revises: 0001_m0_identity
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_approval_policy"
down_revision: str | None = "0001_m0_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS approval_policy")

    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_object_type", sa.Text(), nullable=False),
        sa.Column("target_object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_payload", postgresql.JSONB(), nullable=False),
        sa.Column("param_hash", sa.Text(), nullable=False),
        sa.Column("card_payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("execution_result", sa.Text(), nullable=True),
        sa.Column("initiator_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalate_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expired_reason", sa.Text(), nullable=True),
        sa.Column("origin_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_initiator_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_ref", sa.Text(), nullable=True),
        sa.Column("side_effect_level", sa.Text(), nullable=False),
        schema="approval_policy",
    )
    op.create_index(
        "ix_approval_requests_org_status_expires",
        "approval_requests",
        ["organization_id", "status", "expires_at"],
        unique=False,
        schema="approval_policy",
    )
    op.create_index(
        "ix_approval_requests_org_initiator",
        "approval_requests",
        ["organization_id", "initiator_id"],
        unique=False,
        schema="approval_policy",
    )
    op.create_index(
        "ix_approval_requests_org_target",
        "approval_requests",
        ["organization_id", "target_object_type", "target_object_id"],
        unique=False,
        schema="approval_policy",
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
            name="uq_approval_policy_idempotency_org_command_key",
        ),
        schema="approval_policy",
    )


def downgrade() -> None:
    op.drop_table("command_idempotency_records", schema="approval_policy")
    op.drop_table("approval_requests", schema="approval_policy")
    op.execute("DROP SCHEMA IF EXISTS approval_policy")
