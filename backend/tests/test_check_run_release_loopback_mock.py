"""Loopback mock HTTP for GitHub check runs and release prepare."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub import repository as connector_repo
from app.modules.quality_gates.check_run_stub import sync_check_run_stub
from tests.test_api_120_action_previews import _seed_admin_peer
from tests.test_api_150_155_release import (
    _approve_as_admin,
    _create_release_push_approval,
    _create_task,
    _poll_task_status,
    _seed_jira_connector,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_MOCK_PATH = _BACKEND_ROOT / "scripts" / "mock_integrations.py"


def _load_mock_module() -> Any:
    spec = importlib.util.spec_from_file_location("mock_integrations", _MOCK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mock_integrations"] = module
    spec.loader.exec_module(module)
    return module


mock_integrations = _load_mock_module()


def _asgi_transport() -> ASGITransport:
    mock_integrations.reset_state()
    return ASGITransport(app=mock_integrations.app)


def _patch_module_httpx(module_path: str, transport: httpx.BaseTransport) -> Any:
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return patch(f"{module_path}.httpx.AsyncClient", factory)


async def _seed_github_loopback_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type="github",
        name="Local mock GitHub",
        credential_ref="env:GITHUB_WEBHOOK_SECRET",
        outbound_write_enabled=True,
        action_contract={
            "base_url": "http://127.0.0.1:8091/github",
            "owner": "local-dev",
            "repo": "demo",
            "sideEffectLevel": "L2",
        },
    )
    await db_session.commit()
    return connector.id


async def _seed_release_loopback_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type="release",
        name="Local mock Release",
        credential_ref="env:JENKINS_API_TOKEN",
        outbound_write_enabled=True,
        webhook_secret_ref="env:GITHUB_WEBHOOK_SECRET",
        action_contract={
            "base_url": "http://127.0.0.1:8091/release",
            "sideEffectLevel": "L2",
        },
    )
    await db_session.commit()
    return connector.id


@pytest.mark.asyncio
async def test_check_run_loopback_syncs_completed_check_run(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await _seed_github_loopback_connector(db_session, org_id=org_id, user_id=user_id)

    evaluation_id = uuid.uuid4()
    transport = _asgi_transport()
    with _patch_module_httpx("app.modules.quality_gates.check_run_stub", transport):
        ref = await sync_check_run_stub(
            db_session,
            organization_id=org_id,
            evaluation_id=evaluation_id,
            evaluation_result="pass",
            check_run_ref=None,
            request_hash="loopback-check-run",
            policy_mode="blocking",
        )

    assert ref["sync_status"] == "completed"
    assert ref["conclusion"] == "success"
    assert ref.get("external_check_id") is not None
    check_id = ref["external_check_id"]
    stored = mock_integrations._state.check_runs[check_id]
    assert stored.status == "completed"
    assert stored.conclusion == "success"
    assert stored.owner == "local-dev"
    assert stored.repo == "demo"


@pytest.mark.asyncio
async def test_check_run_loopback_http_failure_sets_sync_failed(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await _seed_github_loopback_connector(db_session, org_id=org_id, user_id=user_id)
    mock_integrations.reset_state()

    def fail_handler(request: httpx.Request) -> Response:
        return Response(500, json={"detail": "mock failure"})

    transport = httpx.MockTransport(fail_handler)
    evaluation_id = uuid.uuid4()
    with _patch_module_httpx("app.modules.quality_gates.check_run_stub", transport):
        ref = await sync_check_run_stub(
            db_session,
            organization_id=org_id,
            evaluation_id=evaluation_id,
            evaluation_result="fail",
            check_run_ref=None,
            request_hash="loopback-check-run-fail",
            policy_mode="blocking",
        )

    assert ref["sync_status"] == "failed"
    assert mock_integrations._state.check_runs == {}


@pytest.mark.asyncio
async def test_release_loopback_prepare_after_approval(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await _seed_jira_connector(db_session, org_id=org_id, user_id=user_id)
    await _seed_release_loopback_connector(db_session, org_id=org_id, user_id=user_id)
    await _seed_admin_peer(db_session, org_id=org_id, project_id=project_id)

    create = await _create_task(client, project_id=project_id)
    assert create.status_code == 201, create.text
    task_id = str(create.json()["data"]["id"])
    await _poll_task_status(client, task_id, wanted={"PENDING_CONFIRM"})

    transport = _asgi_transport()
    with _patch_module_httpx("app.modules.release_orchestration.service", transport):
        approval_id = await _create_release_push_approval(client, task_id, project_id)
        decision = await _approve_as_admin(client, db_session, seeded_identity, approval_id)
        assert decision.status_code == 200, decision.text
        assert decision.json()["data"]["execution_result"] == "ok"

    task = await _poll_task_status(client, task_id, wanted={"SUBMITTED"})
    release_item = task["scope_snapshot"].get("release_item")
    assert release_item is not None
    assert release_item["external_system"] == "release_mock"
    assert release_item["external_item_id"].startswith("RI-")
    assert mock_integrations._state.release_items
