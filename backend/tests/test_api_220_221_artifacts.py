"""API-220/221 and Playwright web evidence tests (S-M2-01)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import object_store
from app.modules.results_evidence import repository as evidence_repo
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _start_body
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case


def test_object_store_rejects_path_traversal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(ValueError, match="invalid_object_key"):
        object_store.resolve_path("../secret.bin")
    with pytest.raises(ValueError, match="invalid_object_key"):
        object_store.resolve_path("org/../../etc/passwd")


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 80,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.1)
    raise AssertionError(f"run did not reach {wanted}")


async def create_active_web_case(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    title: str = "Web case",
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "web",
            "execution_mode": "script",
            "title": title,
            "drafts": [
                {
                    "steps": steps
                    or [
                        {"action": "goto", "params": {"url": "https://example.com"}},
                        {"action": "click", "params": {"selector": "#missing"}},
                    ],
                    "assertions": [],
                }
            ],
        },
    )
    assert create.status_code == 201, create.text
    case_id = create.json()["data"]["id"]
    version = create.json()["data"]["version"]
    submit = await client.post(
        f"/api/v1/test-cases/{case_id}/submit-review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    assert submit.status_code == 200, submit.text
    pending_version = submit.json()["data"]["version"]
    approve = await client.post(
        f"/api/v1/test-cases/{case_id}/review",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": pending_version, "decision": "approve"},
    )
    assert approve.status_code == 200, approve.text
    return approve.json()["data"]


async def _seed_artifact(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    classification: str = "Confidential",
    write_file: bool = True,
    checksum_override: str | None = None,
) -> dict[str, object]:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    from datetime import UTC, datetime

    from app.modules.run_orchestration.models import TestRun

    now = datetime.now(UTC)
    run = TestRun(
        id=uuid.uuid4(),
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        project_id=project_id,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": []},
        result_summary={},
    )
    db_session.add(run)
    await db_session.flush()
    case_result = await evidence_repo.insert_case_result(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        test_run_id=run.id,
        test_case_id=uuid.uuid4(),
        test_case_version_id=None,
        attempt_seq=1,
        outcome="failed",
        is_late=False,
        is_partial=False,
        chunk_key=None,
        normalized_summary=None,
        data_classification="Internal",
    )
    artifact_id = uuid.uuid4()
    data = b"artifact-bytes"
    object_key = object_store.generate_object_key(
        organization_id=org_id,
        artifact_id=artifact_id,
        filename="trace.zip",
    )
    checksum = (
        object_store.write_bytes(object_key=object_key, data=data) if write_file else "deadbeef"
    )
    if checksum_override is not None:
        checksum = checksum_override
    row = await evidence_repo.insert_artifact(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        case_result_id=case_result.id,
        test_run_id=run.id,
        kind="trace",
        object_key=object_key,
        checksum=checksum,
        byte_size=len(data),
        mime_type="application/zip",
        data_classification=classification,
        original_filename="trace.zip",
        artifact_id=artifact_id,
    )
    await db_session.commit()
    return {
        "artifact_id": str(row.id),
        "object_key": object_key,
        "test_run_id": str(run.id),
        "project_id": str(seeded_identity["project_id"]),
    }


@pytest.mark.asyncio
async def test_api_220_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity)
    await login_as(client)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["kind"] == "trace"
    assert data["scan_status"] == "passed"
    assert data["content_access"]["mode"] == "app_proxy"
    assert data["content_access"]["content_path"].endswith("/content")


@pytest.mark.asyncio
async def test_api_221_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity)
    await login_as(client)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}/content")
    assert response.status_code == 200
    assert response.content == b"artifact-bytes"
    assert "attachment" in response.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_api_220_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_artifact(db_session, seeded_identity)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_221_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    seeded = await _seed_artifact(db_session, seeded_identity)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}/content")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_220_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity)
    from datetime import UTC, datetime

    from app.modules.identity_tenancy.models import Organization, Project, ProjectMember, User

    now = datetime.now(UTC)
    other_org = Organization(
        id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
        created_by=None,
        aggregate_version=1,
        name="Other Org",
        slug="other-org",
        capability_controls={},
        siem_export={},
        is_active=True,
    )
    other_user = User(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        created_at=now,
        updated_at=now,
        created_by=uuid.uuid4(),
        aggregate_version=1,
        idp_subject="other-subject",
        display_name="Other",
        email="other@example.com",
        is_disabled=False,
    )
    other_user.created_by = other_user.id
    other_project = Project(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        created_at=now,
        updated_at=now,
        created_by=other_user.id,
        aggregate_version=1,
        name="Other Project",
        jira_project_key=None,
        jira_sync_cursor=None,
        bind_env_ids=None,
    )
    other_member = ProjectMember(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        created_at=now,
        updated_at=now,
        created_by=other_user.id,
        aggregate_version=1,
        project_id=other_project.id,
        user_id=other_user.id,
        role="owner",
    )
    db_session.add(other_org)
    await db_session.flush()
    db_session.add(other_user)
    await db_session.flush()
    db_session.add(other_project)
    await db_session.flush()
    db_session.add(other_member)
    await db_session.commit()
    await login_as(client, idp_subject="other-subject")
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_object_key_not_usable_as_content_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity)
    await login_as(client)
    response = await client.get(f"/api/v1/{seeded['object_key']}")
    assert response.status_code in {404, 401}


@pytest.mark.asyncio
async def test_api_221_restricted_policy_deny(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity, classification="Restricted")
    await login_as(client)
    meta = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}")
    assert meta.status_code == 200
    content = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}/content")
    assert content.status_code == 403
    assert content.json()["error"]["code"] == "HT-POL-001"


@pytest.mark.asyncio
async def test_api_221_missing_file_state(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(db_session, seeded_identity, write_file=False)
    await login_as(client)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}/content")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_221_checksum_mismatch(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_artifact(
        db_session,
        seeded_identity,
        checksum_override="0" * 64,
    )
    await login_as(client)
    response = await client.get(f"/api/v1/artifacts/{seeded['artifact_id']}/content")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-003"


@pytest.mark.asyncio
async def test_failed_web_step_has_trace(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = mock_oidc_token_exchange
    monkeypatch.setenv("PLAYWRIGHT_WORKER_STUB", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_web_case(client, project_id=project_id)
    await login_as(client)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            **_start_body(
                project_id=project_id,
                env_id=env["id"],
                case_ids=[case["id"]],
                expected_env_version=env["version"],
            ),
            "params": {"TARGET_ENV": "https://example.test"},
        },
    )
    assert start.status_code == 200
    await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED", "SUCCEEDED"})
    results = await client.get(
        f"/api/v1/test-runs/{start.json()['data']['id']}/case-results",
    )
    case_result_id = results.json()["data"]["items"][0]["id"]
    detail = await client.get(f"/api/v1/case-results/{case_result_id}")
    artifact_ids = detail.json()["data"]["artifact_ids"]
    assert artifact_ids
    steps = await client.get(f"/api/v1/case-results/{case_result_id}/step-runs")
    failed = [item for item in steps.json()["data"]["items"] if item.get("observation_ref")]
    assert failed, "failed web step must expose trace observation_ref"
    trace_meta = None
    for artifact_id in artifact_ids:
        meta = await client.get(f"/api/v1/artifacts/{artifact_id}")
        assert meta.status_code == 200
        if meta.json()["data"]["kind"] == "trace":
            trace_meta = meta
            trace_id = artifact_id
            break
    assert trace_meta is not None
    trace_content = await client.get(f"/api/v1/artifacts/{trace_id}/content")
    assert trace_content.status_code == 200
    assert len(trace_content.content) > 0


@pytest.mark.asyncio
async def test_api_script_httpx_regression(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    from unittest.mock import AsyncMock, patch

    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    with patch("app.modules.run_orchestration.executor.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_client
        start = await client.post(
            "/api/v1/test-runs",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={
                **_start_body(
                    project_id=project_id,
                    env_id=env["id"],
                    case_ids=[case["id"]],
                    expected_env_version=env["version"],
                ),
                "params": {"TARGET_ENV": "https://example.test"},
            },
        )
    await _poll_run_status(client, start.json()["data"]["id"], wanted={"SUCCEEDED"})
    assert mock_client.request.called
