"""S-M0-01: "no tenant context = reject" must hold — never fall back to a default.

Covers the three gaps found in the S-M0-01 review:

1. Protected endpoints reject an unauthenticated caller with 401, not 404.
2. The tenant is derived only from the auth session; there is no default-tenant
   fallback when the session points nowhere.
3. The membership-gated endpoints (403 ``HT-IAM-001``) are actually exercised —
   previously they had no test at all.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.models import ProjectMember
from app.modules.identity_tenancy.service import load_session_context
from tests.helpers import login_as

# Endpoints guarded by require_session_with_membership.
MEMBERSHIP_GATED: tuple[tuple[str, str], ...] = (
    ("GET", "/api/v1/organizations/current"),
    ("POST", "/api/v1/organizations/current/capability-controls/tighten"),
    ("PUT", "/api/v1/organizations/current/siem-export"),
    ("GET", "/api/v1/org-quotas/current"),
)

# A representative slice of session-guarded endpoints.
SESSION_GUARDED: tuple[str, ...] = (
    "/api/v1/organizations/current",
    "/api/v1/org-quotas/current",
    "/api/v1/me",
    "/api/v1/projects",
    "/api/v1/test-plans",
    "/api/v1/audit-events",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", SESSION_GUARDED)
async def test_protected_endpoint_without_session_is_401_not_404(
    client: AsyncClient, path: str
) -> None:
    """api_spec §2.6: unauthenticated must be 401 HT-AUTH-001, never a 404 masquerade."""
    response = await client.get(path)
    assert response.status_code == 401, f"{path} returned {response.status_code}"
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_session_tenant_comes_from_session_not_a_default(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = uuid.UUID(str(seeded_identity["org_id"]))
    user_id = uuid.UUID(str(seeded_identity["user_id"]))
    auth_session = await repo.create_auth_session(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        last_reauth_at=None,
    )
    await db_session.commit()

    ctx = await load_session_context(db_session, auth_session)

    assert ctx is not None
    assert ctx.organization.id == org_id


@pytest.mark.asyncio
async def test_session_pointing_at_unknown_org_is_rejected(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    """No tenant context must resolve to None — not to some default organization."""
    user_id = uuid.UUID(str(seeded_identity["user_id"]))
    auth_session = await repo.create_auth_session(
        db_session,
        organization_id=uuid.uuid4(),
        user_id=user_id,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        last_reauth_at=None,
    )
    await db_session.commit()

    assert await load_session_context(db_session, auth_session) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "path"), MEMBERSHIP_GATED)
async def test_membership_gated_endpoint_rejects_user_without_membership(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    method: str,
    path: str,
) -> None:
    """A valid session in an org with zero project memberships is 403 HT-IAM-001."""
    org_id = uuid.UUID(str(seeded_identity["org_id"]))
    user_id = uuid.UUID(str(seeded_identity["user_id"]))
    await login_as(client)

    await db_session.execute(
        delete(ProjectMember).where(
            ProjectMember.organization_id == org_id,
            ProjectMember.user_id == user_id,
        )
    )
    await db_session.commit()

    if method == "GET":
        response = await client.get(path)
    else:
        response = await client.request(method, path, json={})

    assert response.status_code == 403, f"{method} {path} returned {response.status_code}"
    assert response.json()["error"]["code"] == "HT-IAM-001"
