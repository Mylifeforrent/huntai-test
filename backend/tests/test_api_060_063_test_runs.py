import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.execution_registry import repository as env_repo
from app.modules.run_orchestration import repository as run_repo
from app.modules.run_orchestration.service import reclaim_stale_active_runs
from tests.helpers import login_as
from tests.test_api_100_106_env_registry import _register_environment
from tests.test_api_120_action_previews import _seed_admin_peer


async def _activate_environment(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    name: str = "CI Staging",
) -> dict[str, object]:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    created = await _register_environment(client, project_id, name=name)
    approval_id = created["approval_request_id"]
    await login_as(client, idp_subject="admin-peer-120")
    detail = await client.get(f"/api/v1/approval-requests/{approval_id}")
    version = detail.json()["data"]["version"]
    await client.post(
        f"/api/v1/approval-requests/{approval_id}/decisions",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"decision": "approve", "expected_version": version},
    )
    await login_as(client)
    env = await client.get(f"/api/v1/execution-environments/{created['id']}")
    assert env.json()["data"]["status"] == "ACTIVE"
    return env.json()["data"]


def _start_body(
    *,
    project_id: uuid.UUID,
    env_id: str,
    case_ids: list[str] | None = None,
    execution_source: str = "script",
    expected_env_version: int | None = None,
    trigger_type: str = "manual",
) -> dict[str, object]:
    body: dict[str, object] = {
        "project_id": str(project_id),
        "env_id": env_id,
        "execution_source": execution_source,
        "case_ids": case_ids or [str(uuid.uuid4())],
        "trigger_type": trigger_type,
    }
    if expected_env_version is not None:
        body["expected_env_version"] = expected_env_version
    return body


@pytest.mark.asyncio
async def test_api_060_unauthenticated(client: AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/test-runs?project_id={uuid.uuid4()}",
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_062_viewer_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    from tests.test_api_120_action_previews import _seed_viewer

    await _seed_viewer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
        idp_subject="viewer-run",
    )
    await login_as(client, idp_subject="viewer-run")
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(project_id=project_id, env_id=env["id"]),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_062_env_not_active(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    created = await _register_environment(client, project_id)
    assert created["status"] == "PENDING_APPROVAL"
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(project_id=project_id, env_id=created["id"]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_062_project_scoped_env_mismatch_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity, name="Other Project Env")
    bound = await env_repo.get_environment(
        db_session,
        organization_id=org_id,
        environment_id=uuid.UUID(str(env["id"])),
    )
    assert bound is not None
    bound.scope_level = "project"
    bound.project_id = uuid.uuid4()
    await db_session.commit()

    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(project_id=project_id, env_id=str(env["id"])),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_062_agent_external_ci_validation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(
            project_id=project_id,
            env_id=env["id"],
            execution_source="agent",
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_062_happy_start_pending(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    case_id = str(uuid.uuid4())
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(
            project_id=project_id,
            env_id=env["id"],
            case_ids=[case_id],
            expected_env_version=env["version"],
        ),
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "PENDING"
    assert data["status"] != "SUCCEEDED"
    assert data["gate_evaluation_id"] is None
    assert "credential_ref" not in str(data)
    snapshot = data["snapshot_summary"]
    assert snapshot["case_ids"] == [case_id]
    assert snapshot["env_config_version"] == env["config_version"]

    detail = await client.get(f"/api/v1/test-runs/{data['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "PENDING"
    assert detail.json()["data"]["snapshot_summary"]["case_ids"] == [case_id]


@pytest.mark.asyncio
async def test_api_062_idempotent_start(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    key = str(uuid.uuid4())
    body = _start_body(project_id=project_id, env_id=env["id"])
    first = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": key},
        json=body,
    )
    second = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": key},
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


@pytest.mark.asyncio
async def test_api_063_cancel_pending_and_replay(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(project_id=project_id, env_id=env["id"]),
    )
    run_id = start.json()["data"]["id"]
    version = start.json()["data"]["version"]
    key = str(uuid.uuid4())
    cancel_body = {"expected_version": version}
    first = await client.post(
        f"/api/v1/test-runs/{run_id}/cancel",
        headers={"Idempotency-Key": key},
        json=cancel_body,
    )
    assert first.status_code == 200
    assert first.json()["data"]["test_run"]["status"] == "CANCELLED"
    assert first.json()["data"]["receipt"]["command_type"] == "test_run.cancel"
    second = await client.post(
        f"/api/v1/test-runs/{run_id}/cancel",
        headers={"Idempotency-Key": key},
        json=cancel_body,
    )
    assert second.status_code == 200
    assert second.json()["data"]["receipt"]["id"] == first.json()["data"]["receipt"]["id"]


@pytest.mark.asyncio
async def test_api_063_cancel_terminal_state(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    start = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(project_id=project_id, env_id=env["id"]),
    )
    run_id = start.json()["data"]["id"]
    version = start.json()["data"]["version"]
    await client.post(
        f"/api/v1/test-runs/{run_id}/cancel",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    detail = await client.get(f"/api/v1/test-runs/{run_id}")
    new_version = detail.json()["data"]["version"]
    response = await client.post(
        f"/api/v1/test-runs/{run_id}/cancel",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": new_version},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_060_include_waiting_dwell_seconds(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    now = datetime.now(UTC) - timedelta(seconds=120)
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=seeded_identity["user_id"],  # type: ignore[arg-type]
        project_id=project_id,
        plan_id=None,
        env_id=uuid.UUID(env["id"]),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_APPROVAL",
        snapshot={
            "case_ids": [str(uuid.uuid4())],
            "env_id": env["id"],
            "env_config_version": 1,
            "execution_source": "script",
            "trigger_type": "manual",
            "params_redacted": {},
        },
    )
    run.updated_at = now
    await db_session.commit()

    all_resp = await client.get(
        f"/api/v1/test-runs?project_id={project_id}&include_waiting=true",
    )
    assert all_resp.status_code == 200
    items = all_resp.json()["data"]["items"]
    match = next(item for item in items if item["id"] == str(run.id))
    assert match["dwell_seconds"] >= 120

    filtered = await client.get(
        f"/api/v1/test-runs?project_id={project_id}&include_waiting=false",
    )
    assert filtered.status_code == 200
    filtered_ids = {item["id"] for item in filtered.json()["data"]["items"]}
    assert str(run.id) not in filtered_ids


@pytest.mark.asyncio
async def test_api_061_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await _activate_environment(client, db_session, seeded_identity)
    response = await client.get(f"/api/v1/test-runs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_reclaim_stale_active_runs(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    env_id = uuid.uuid4()
    now = datetime.now(UTC)
    stale = now - timedelta(seconds=600)
    snapshot_stub = {
        "case_ids": [],
        "env_id": str(env_id),
        "env_config_version": 1,
        "params_redacted": {},
    }
    running = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=stale,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="RUNNING",
        snapshot=snapshot_stub,
    )
    running.last_heartbeat_at = stale
    waiting = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=stale,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="WAITING_APPROVAL",
        snapshot=snapshot_stub,
    )
    waiting.updated_at = stale
    await db_session.commit()

    count = await reclaim_stale_active_runs(
        db_session,
        now=now,
        heartbeat_timeout_seconds=300,
        organization_id=org_id,
    )
    assert count == 1
    await db_session.refresh(running)
    await db_session.refresh(waiting)
    assert running.status == "TIMEOUT"
    assert waiting.status == "WAITING_APPROVAL"


@pytest.mark.asyncio
async def test_api_062_ci_webhook_trigger_rejected(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await _activate_environment(client, db_session, seeded_identity)
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_start_body(
            project_id=project_id,
            env_id=env["id"],
            trigger_type="ci_webhook",
        ),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"
