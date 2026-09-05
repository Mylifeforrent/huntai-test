"""case_results chunk_key partial unique index (already in 0013)

Revision ID: 0021_case_result_chunk_unique
Revises: 0020_ci_trigger_bindings
Create Date: 2026-09-04
"""

from collections.abc import Sequence

revision: str = "0021_case_result_chunk_unique"
down_revision: str | None = "0020_ci_trigger_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0013 已建 partial unique `ix_case_results_org_run_chunk_key`
    # (organization_id, test_run_id, chunk_key) WHERE chunk_key IS NOT NULL。
    # 本修订仅保持 alembic 链连续，禁止再建第二套同列 unique 索引。
    return


def downgrade() -> None:
    return
