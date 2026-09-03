"""M0 identity_tenancy and audit_events schemas

Revision ID: 0001_m0_identity
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_m0_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CAPABILITY_CONTROLS = (
    '{"ai_global_tightened": false, "tightened_capabilities": [], "tightened_modules": []}'
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity_tenancy")
    op.execute("CREATE SCHEMA IF NOT EXISTS results_evidence")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "capability_controls",
            postgresql.JSONB(),
            nullable=False,
            server_default=DEFAULT_CAPABILITY_CONTROLS,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_organizations_slug",
        "organizations",
        ["slug"],
        unique=True,
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_organizations_is_active",
        "organizations",
        ["is_active"],
        unique=False,
        schema="identity_tenancy",
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("idp_subject", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("is_disabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["identity_tenancy.organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "idp_subject", name="uq_users_org_idp_subject"),
        schema="identity_tenancy",
    )
    op.create_index(
        "uq_users_org_email",
        "users",
        ["organization_id", "email"],
        unique=True,
        schema="identity_tenancy",
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("jira_project_key", sa.Text(), nullable=True),
        sa.Column("jira_sync_cursor", sa.Text(), nullable=True),
        sa.Column("bind_env_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["identity_tenancy.organizations.id"],
            ondelete="RESTRICT",
        ),
        schema="identity_tenancy",
    )
    op.create_index(
        "uq_projects_org_jira_key",
        "projects",
        ["organization_id", "jira_project_key"],
        unique=True,
        schema="identity_tenancy",
        postgresql_where=sa.text("jira_project_key IS NOT NULL"),
    )
    op.create_index(
        "ix_projects_org_name",
        "projects",
        ["organization_id", "name"],
        unique=False,
        schema="identity_tenancy",
    )

    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["identity_tenancy.projects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_tenancy.users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "project_id",
            "user_id",
            name="uq_project_members_org_project_user",
        ),
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_project_members_org_user",
        "project_members",
        ["organization_id", "user_id"],
        unique=False,
        schema="identity_tenancy",
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_outbox_org_event_id"),
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox_events",
        ["organization_id"],
        unique=False,
        schema="identity_tenancy",
        postgresql_where=sa.text("published_at IS NULL"),
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
            name="uq_idempotency_org_command_key",
        ),
        schema="identity_tenancy",
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reauth_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["identity_tenancy.users.id"],
            ondelete="RESTRICT",
        ),
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_auth_sessions_org_user",
        "auth_sessions",
        ["organization_id", "user_id"],
        unique=False,
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_auth_sessions_expires_active",
        "auth_sessions",
        ["expires_at"],
        unique=False,
        schema="identity_tenancy",
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "oidc_login_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("nonce", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("return_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_oidc_drafts_state",
        "oidc_login_drafts",
        ["state"],
        unique=True,
        schema="identity_tenancy",
    )
    op.create_index(
        "ix_oidc_drafts_expires_unconsumed",
        "oidc_login_drafts",
        ["expires_at"],
        unique=False,
        schema="identity_tenancy",
        postgresql_where=sa.text("consumed_at IS NULL"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delegated_agent", sa.Text(), nullable=True),
        sa.Column("workflow", sa.Text(), nullable=True),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("skill_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("tool", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("resource_type", sa.Text(), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_hash", sa.Text(), nullable=True),
        sa.Column("response_hash", sa.Text(), nullable=True),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_decision", sa.Text(), nullable=True),
        sa.Column("approval_bound_hash", sa.Text(), nullable=True),
        sa.Column("data_classification", sa.Text(), nullable=False),
        sa.Column("external_request_id", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("cost", sa.Numeric(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("payload_ref", sa.Text(), nullable=True),
        schema="results_evidence",
    )
    op.create_index(
        "ix_audit_org_created",
        "audit_events",
        ["organization_id", "created_at"],
        unique=False,
        schema="results_evidence",
    )
    op.create_index(
        "ix_audit_org_actor_created",
        "audit_events",
        ["organization_id", "actor_user_id", "created_at"],
        unique=False,
        schema="results_evidence",
    )
    op.create_index(
        "ix_audit_org_request_hash",
        "audit_events",
        ["organization_id", "request_hash"],
        unique=False,
        schema="results_evidence",
    )
    op.create_index(
        "ix_audit_org_approval",
        "audit_events",
        ["organization_id", "approval_id"],
        unique=False,
        schema="results_evidence",
    )
    op.create_index(
        "ix_audit_org_external_request",
        "audit_events",
        ["organization_id", "external_request_id"],
        unique=False,
        schema="results_evidence",
        postgresql_where=sa.text("external_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("audit_events", schema="results_evidence")
    op.drop_table("oidc_login_drafts", schema="identity_tenancy")
    op.drop_table("auth_sessions", schema="identity_tenancy")
    op.drop_table("command_idempotency_records", schema="identity_tenancy")
    op.drop_table("outbox_events", schema="identity_tenancy")
    op.drop_table("project_members", schema="identity_tenancy")
    op.drop_table("projects", schema="identity_tenancy")
    op.drop_table("users", schema="identity_tenancy")
    op.drop_table("organizations", schema="identity_tenancy")
    op.execute("DROP SCHEMA IF EXISTS results_evidence CASCADE")
    op.execute("DROP SCHEMA IF EXISTS identity_tenancy CASCADE")
