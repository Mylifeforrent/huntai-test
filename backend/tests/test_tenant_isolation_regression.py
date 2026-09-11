"""S-M0-01: AC-003 tenant-isolation sweep at the API boundary.

Two systemic invariants that per-resource tests do not cover:

1. A caller must never learn whether a resource exists outside their tenant: a
   non-existent / cross-tenant id yields 404 ``HT-RES-001``, never 403 or 404
   differences that leak existence (api_spec §2.6).
2. Tenant-scoped collections must not surface another tenant's rows.

Per-resource cross-tenant tests already live next to their endpoints; this file
sweeps the whole detail surface uniformly so a new endpoint cannot quietly
diverge.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.modules.test_assets import models as test_assets_models
from tests.helpers import login_as

# Every GET detail route that resolves a tenant-scoped resource by id.
DETAIL_PATHS: tuple[str, ...] = (
    "/api/v1/action-previews/{id}",
    "/api/v1/ai-invocation-logs/{id}",
    "/api/v1/ai/generations/{id}",
    "/api/v1/ai/generations/{id}/drafts",
    "/api/v1/approval-requests/{id}",
    "/api/v1/artifacts/{id}",
    "/api/v1/audit-events/{id}",
    "/api/v1/case-results/{id}",
    "/api/v1/case-results/{id}/step-runs",
    "/api/v1/command-receipts/{id}",
    "/api/v1/connectors/{id}",
    "/api/v1/copilot-sessions/{id}",
    "/api/v1/evidence-objects/{id}",
    "/api/v1/execution-environments/{id}",
    "/api/v1/execution-environments/{id}/health",
    "/api/v1/execution-environments/{id}/jobs",
    "/api/v1/execution-environments/{id}/jobs/{id}/params-schema",
    "/api/v1/failure-clusters/{id}",
    "/api/v1/failure-clusters/{id}/similar",
    "/api/v1/gate-evaluations/{id}",
    "/api/v1/import-sources/{id}",
    "/api/v1/perf-baselines/{id}",
    "/api/v1/projects/{id}",
    "/api/v1/projects/{id}/execution-options",
    "/api/v1/projects/{id}/members",
    "/api/v1/projects/{id}/quota-view",
    "/api/v1/quality-gate-policies/{id}",
    "/api/v1/release-tasks/{id}",
    "/api/v1/release-tasks/{id}/readiness",
    "/api/v1/test-cases/{id}",
    "/api/v1/test-cases/{id}/versions",
    "/api/v1/test-cases/{id}/versions/{id}",
    "/api/v1/test-plans/{id}",
    "/api/v1/test-runs/{id}",
    "/api/v1/test-runs/{id}/case-results",
    "/api/v1/test-runs/{id}/failure-clusters",
    "/api/v1/test-runs/{id}/gate-evaluation",
    "/api/v1/test-runs/{id}/trajectory",
)


def _materialize(path: str) -> str:
    return path.replace("{id}", str(uuid.uuid4()))


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DETAIL_PATHS)
async def test_unknown_id_is_not_found_never_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    path: str,
) -> None:
    """Authenticated callers get 404 HT-RES-001; existence is never disclosed."""
    _ = seeded_identity
    await login_as(client)

    response = await client.get(_materialize(path))

    assert response.status_code == 404, (
        f"{path} leaked existence with status {response.status_code}: {response.text[:200]}"
    )
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_unauthenticated_detail_access_is_401_not_404(
    client: AsyncClient,
) -> None:
    """No session must be 401 HT-AUTH-001 — never a 404 masquerade (api_spec §2.6)."""
    response = await client.get(f"/api/v1/test-plans/{uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_other_tenant_project_cannot_be_enumerated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    """Supplying another tenant's project id must 404, not enumerate its plans."""
    _ = seeded_identity
    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    other_project = uuid.uuid4()
    foreign_plan = uuid.uuid4()

    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Foreign Org",
            slug="foreign-org-isolation",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=other_user,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            idp_subject="foreign-isolation-user",
            display_name="Foreign",
            email="foreign-isolation@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=other_project,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            name="Foreign Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            user_id=other_user,
            role="owner",
        )
    )
    db_session.add(
        test_assets_models.TestPlan(
            id=foreign_plan,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            project_id=other_project,
            name="Foreign secret plan",
            jira_fix_version=None,
            schedule_binding=None,
        )
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get("/api/v1/test-plans", params={"project_id": str(other_project)})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"
    assert str(foreign_plan) not in response.text
