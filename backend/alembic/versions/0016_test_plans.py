"""test_plans and test_plan_cases

Revision ID: 0016_test_plans
Revises: 0015_evidence_objects
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_test_plans"
down_revision: str | None = "0015_evidence_objects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("jira_fix_version", sa.Text(), nullable=True),
        sa.Column(
            "schedule_binding",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        schema="test_assets",
    )
    op.create_index(
        "ix_test_plans_org_project",
        "test_plans",
        ["organization_id", "project_id"],
        schema="test_assets",
    )

    op.create_table(
        "test_plan_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("test_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["test_plan_id"],
            ["test_assets.test_plans.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "test_plan_id",
            "test_case_id",
            name="uq_test_plan_cases_org_plan_case",
        ),
        schema="test_assets",
    )


def downgrade() -> None:
    op.drop_table("test_plan_cases", schema="test_assets")
    op.drop_index(
        "ix_test_plans_org_project",
        table_name="test_plans",
        schema="test_assets",
    )
    op.drop_table("test_plans", schema="test_assets")
