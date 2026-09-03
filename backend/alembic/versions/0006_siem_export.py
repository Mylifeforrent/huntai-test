"""organizations.siem_export JSONB projection

Revision ID: 0006_siem_export
Revises: 0005_quota_governance
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_siem_export"
down_revision: str | None = "0005_quota_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_SIEM_EXPORT = '{"enabled": false}'


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "siem_export",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=DEFAULT_SIEM_EXPORT,
        ),
        schema="identity_tenancy",
    )


def downgrade() -> None:
    op.drop_column("organizations", "siem_export", schema="identity_tenancy")
