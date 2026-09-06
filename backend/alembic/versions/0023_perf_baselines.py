"""perf_baselines table and perf concurrency in-use counter (S-M3-01)

Revision ID: 0023_perf_baselines
Revises: 0022_artifact_export_receipt
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_perf_baselines"
down_revision: str | None = "0022_artifact_export_receipt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "perf_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column(
            "scenario_test_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("test_assets.test_cases.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("tolerance", postgresql.JSONB(), nullable=False),
        sa.Column("latest_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="test_assets",
    )
    op.create_index(
        "ix_perf_baselines_org_scenario",
        "perf_baselines",
        ["organization_id", "scenario_test_case_id"],
        schema="test_assets",
    )
    op.create_index(
        "uq_perf_baselines_active_scenario",
        "perf_baselines",
        ["organization_id", "scenario_test_case_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE"),
        schema="test_assets",
    )
    op.add_column(
        "org_quotas",
        sa.Column(
            "perf_concurrency_in_use",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema="quota_governance",
    )


def downgrade() -> None:
    op.drop_column(
        "org_quotas",
        "perf_concurrency_in_use",
        schema="quota_governance",
    )
    op.drop_index(
        "uq_perf_baselines_active_scenario",
        table_name="perf_baselines",
        schema="test_assets",
    )
    op.drop_index(
        "ix_perf_baselines_org_scenario",
        table_name="perf_baselines",
        schema="test_assets",
    )
    op.drop_table("perf_baselines", schema="test_assets")
