import os

TEST_ENV: dict[str, str] = {
    "APP_ENV": "test",
    "APP_PORT": "8000",
    "LOG_LEVEL": "warning",
    "DATABASE_URL": os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres@127.0.0.1:5432/huntai_test",
    ),
    "SESSION_COOKIE_NAME": "huntai_session",
    "SESSION_COOKIE_SAMESITE": "Lax",
    "SESSION_COOKIE_SECURE": "true",
    "SESSION_TTL_SECONDS": "3600",
    "OIDC_LOGIN_DRAFT_TTL_SECONDS": "600",
    "REAUTH_WINDOW_SECONDS": "900",
    "OIDC_ISSUER": "https://idp.example.com",
    "OIDC_CLIENT_ID": "test-client",
    "OIDC_CLIENT_SECRET": "test-secret",
    "OIDC_REDIRECT_URI": "http://localhost:8000/api/v1/auth/oidc/callback",
    "OIDC_CLAIM_SUBJECT": "sub",
}

for _key, _value in TEST_ENV.items():
    os.environ[_key] = _value

import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine, get_session_factory
from app.main import create_app
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    Organization,
    Project,
    ProjectMember,
    User,
)


@pytest.fixture(scope="session", autouse=True)
def _set_test_env() -> Generator[None]:
    for key, value in TEST_ENV.items():
        os.environ[key] = value
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def _run_migrations() -> Generator[None]:
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None]:
    engine = get_engine()
    tables = [
        "results_evidence.audit_events",
        "identity_tenancy.oidc_login_drafts",
        "identity_tenancy.auth_sessions",
        "identity_tenancy.command_idempotency_records",
        "identity_tenancy.outbox_events",
        "identity_tenancy.project_members",
        "identity_tenancy.projects",
        "identity_tenancy.users",
        "identity_tenancy.organizations",
    ]
    async with engine.begin() as conn:
        for table in tables:
            await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
    yield


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
async def seeded_identity(db_session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    member_id = uuid.uuid4()

    org = Organization(
        id=org_id,
        created_at=now,
        updated_at=now,
        created_by=None,
        aggregate_version=1,
        name="Test Org",
        slug="test-org",
        capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
        is_active=True,
    )
    user = User(
        id=user_id,
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        idp_subject="test-subject-001",
        display_name="Test User",
        email="user@example.com",
        is_disabled=False,
    )
    project = Project(
        id=project_id,
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        name="Test Project",
        jira_project_key=None,
        jira_sync_cursor=None,
        bind_env_ids=None,
    )
    member = ProjectMember(
        id=member_id,
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        project_id=project_id,
        user_id=user_id,
        role="owner",
    )
    db_session.add(org)
    await db_session.flush()
    db_session.add(user)
    await db_session.flush()
    db_session.add(project)
    await db_session.flush()
    db_session.add(member)
    await db_session.commit()
    return {
        "org_id": org_id,
        "user_id": user_id,
        "project_id": project_id,
        "idp_subject": "test-subject-001",
    }


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        yield ac
    await dispose_engine()
    get_settings.cache_clear()


@pytest.fixture
def mock_oidc_token_exchange() -> Generator[AsyncMock]:
    with (
        patch(
            "app.modules.identity_tenancy.service.exchange_oidc_code",
            new_callable=AsyncMock,
        ) as mock_exchange,
        patch(
            "app.modules.identity_tenancy.service.verify_id_token",
            new_callable=AsyncMock,
        ) as mock_verify,
    ):
        mock_exchange.return_value = {
            "id_token": "verified-by-test-double",
            "access_token": "redacted",
        }

        async def verify_side_effect(
            settings: Any, *, id_token: str, expected_nonce: str
        ) -> dict[str, Any]:
            _ = settings
            _ = id_token
            return {"sub": "test-subject-001", "nonce": expected_nonce}

        mock_verify.side_effect = verify_side_effect
        yield mock_exchange
