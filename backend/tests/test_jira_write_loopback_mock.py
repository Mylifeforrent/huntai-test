"""Jira write via loopback mock (ASGI transport, no TCP)."""

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
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.approval_policy.models import ApprovalRequest
from app.modules.integration_hub import repository as connector_repo
from app.modules.integration_hub.jira_write_stub import JiraWriteSyncError
from app.modules.results_evidence.audit_models import AuditEvent
from app.modules.results_evidence.models import EvidenceObject
from tests.helpers import login_as
from tests.test_api_130_131_039_heal import _start_failed_run
from tests.test_api_jira_write import (
    _approve_as_peer,
    _preview_jira_for_cluster,
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
_RealAsyncClient = httpx.AsyncClient


async def _seed_loopback_jira_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> uuid.UUID:
    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type="jira",
        name="Local mock Jira",
        credential_ref="bound",
        outbound_write_enabled=True,
        action_contract={
            "base_url": "http://127.0.0.1:8091/jira",
            "sideEffectLevel": "L2",
        },
    )
    await db_session.commit()
    return connector.id


def _loopback_httpx_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
    kwargs = dict(kwargs)
    kwargs.setdefault("transport", ASGITransport(app=mock_integrations.app))
    kwargs.setdefault("base_url", "http://127.0.0.1:8091")
    kwargs.setdefault("timeout", 10.0)
    return _RealAsyncClient(*args, **kwargs)


@pytest.mark.asyncio
async def test_loopback_approve_creates_issue_in_mock_store(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    mock_integrations.reset_state()
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await _seed_loopback_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])

    with patch(
        "app.modules.integration_hub.jira_write_stub.httpx.AsyncClient",
        side_effect=_loopback_httpx_client,
    ):
        await _approve_as_peer(client, approval_id=approval_id)

    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status == "EXECUTED"
    assert approval.execution_result == "ok"

    evidence_rows = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    jira_rows = [
        row
        for row in evidence_rows.scalars().all()
        if isinstance(row.source_object, dict) and row.source_object.get("connector") == "jira"
    ]
    assert len(jira_rows) == 1
    source = jira_rows[0].source_object
    assert isinstance(source, dict)
    issue_key = str(source.get("resource", ""))
    assert issue_key.startswith("HT-")

    transport = ASGITransport(app=mock_integrations.app)
    mock_base = "http://127.0.0.1:8091"
    async with _RealAsyncClient(transport=transport, base_url=mock_base) as mock_http:
        fetched = await mock_http.get(f"/jira/rest/api/2/issue/{issue_key}")
    assert fetched.status_code == 200
    assert fetched.json()["key"] == issue_key


@pytest.mark.asyncio
async def test_loopback_mock_500_executed_failed_no_evidence(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    mock_integrations.reset_state()
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    await _seed_loopback_jira_connector(db_session, org_id=org_id, user_id=None)
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster = report["items"][0]
    await login_as(client)
    preview = await _preview_jira_for_cluster(client, project_id=project_id, cluster=cluster)
    approval_id = str(preview["approval_request_id"])

    async def always_fail(**_kwargs: object) -> str:
        raise JiraWriteSyncError("mock HTTP 500")

    with (
        patch(
            "app.modules.integration_hub.jira_write_stub.httpx.AsyncClient",
            side_effect=_loopback_httpx_client,
        ),
        patch(
            "app.modules.integration_hub.jira_write_stub._post_jira_issue_loopback",
            side_effect=always_fail,
        ),
    ):
        await _approve_as_peer(client, approval_id=approval_id)

    approval = await db_session.get(ApprovalRequest, uuid.UUID(approval_id))
    assert approval is not None
    assert approval.status == "EXECUTED"
    assert approval.execution_result == "failed"

    evidence_rows = await db_session.execute(
        select(EvidenceObject).where(
            EvidenceObject.organization_id == org_id,
            EvidenceObject.subject_type == "failure_cluster",
            EvidenceObject.subject_id == uuid.UUID(str(cluster["id"])),
        )
    )
    for row in evidence_rows.scalars().all():
        source = row.source_object if isinstance(row.source_object, dict) else {}
        assert source.get("connector") != "jira"

    audit_rows = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.action == "jira_write.sync_failed",
            AuditEvent.result == "failed",
        )
    )
    assert audit_rows.scalars().first() is not None
