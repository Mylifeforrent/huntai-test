"""connector outbound_channels column (API-165/166)

Revision ID: 0026_connector_outbound_channels
Revises: 0025_copilot_sessions
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026_connector_outbound_channels"
down_revision: str | None = "0025_copilot_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connectors",
        sa.Column(
            "outbound_channels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        schema="integration_hub",
    )


def downgrade() -> None:
    op.drop_column("connectors", "outbound_channels", schema="integration_hub")
