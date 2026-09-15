"""API-064–066, 069, 071, 080, 210 tests for S-M1-02."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.run_orchestration import repository as run_repo
from tests.helpers import login_as
from tests.test_api_060_063_test_runs import _activate_environment, _start_body
from tests.test_api_170_172_api_tokens import _issue_body
from tests.test_run_helpers import activate_platform_executor_env, create_active_script_case


async def _poll_run_status(
    client: AsyncClient,
    run_id: str,
    *,
    wanted: set[str],
    max_attempts: int = 40,
) -> dict[str, object]:
    for _ in range(max_attempts):
        detail = await client.get(f"/api/v1/test-runs/{run_id}")
        assert detail.status_code == 200
        status = detail.json()["data"]["status"]
        if status in wanted:
            return detail.json()["data"]
        await asyncio.sleep(0.05)
    raise AssertionError(f"run did not reach {wanted}")


@pytest.mark.asyncio
async def test_ac_037_accept_pending_then_validating(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
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
        response = await client.post(
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
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "PENDING"
        detail = await _poll_run_status(
            client,
            data["id"],
            wanted={"VALIDATING", "RUNNING", "SUCCEEDED", "FAILED"},
        )
    assert detail["status"] in {"VALIDATING", "RUNNING", "SUCCEEDED", "FAILED"}


@pytest.mark.asyncio
async def test_ac_038_receipt_not_terminal(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    with patch(
        "app.modules.run_orchestration.router.run_test_run_background",
        new_callable=AsyncMock,
    ):
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
    receipt_id = start.json()["data"]["receipt"]["id"]
    receipt = await client.get(f"/api/v1/command-receipts/{receipt_id}")
    assert receipt.status_code == 200
    assert receipt.json()["data"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_ac_041_unresolved_variable_failed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(
        client,
        project_id=project_id,
        steps=[{"action": "request", "params": {"method": "GET", "path": "/{{missing}}"}}],
    )
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
    detail = await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED"})
    assert detail["status"] == "FAILED"
    summary = detail.get("result_summary") or {}
    assert summary.get("reason") == "variable_unresolved"


@pytest.mark.asyncio
async def test_api_064_after_script_run(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok":true}'
    mock_response.headers = {"content-type": "application/json"}
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
        run_id = start.json()["data"]["id"]
        await _poll_run_status(client, run_id, wanted={"SUCCEEDED", "FAILED"})
        results = await client.get(f"/api/v1/test-runs/{run_id}/case-results")
    assert results.status_code == 200
    assert len(results.json()["data"]["items"]) >= 1


@pytest.mark.asyncio
async def test_api_069_only_active_selectable(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _activate_environment(client, db_session, seeded_identity)
    active = await create_active_script_case(client, project_id=project_id, title="active")
    await login_as(client)
    draft = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": "draft-only",
        },
    )
    options = await client.get(f"/api/v1/projects/{project_id}/execution-options")
    assert options.status_code == 200
    cases = options.json()["data"]["cases"]
    by_id = {item["id"]: item for item in cases}
    assert by_id[active["id"]]["selectable"] is True
    assert by_id[draft.json()["data"]["id"]]["selectable"] is False


@pytest.mark.asyncio
async def test_api_080_execute_token_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    issued = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["execute"]),
    )
    token = issued.json()["data"]["token"]
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)
    with patch("app.modules.run_orchestration.executor.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.return_value = mock_client
        response = await client.post(
            "/api/v1/test-runs",
            headers={
                "Idempotency-Key": str(uuid.uuid4()),
                "Authorization": f"Bearer {token}",
            },
            json={
                "project_id": str(project_id),
                "env_id": env["id"],
                "execution_source": "script",
                "case_ids": [case["id"]],
                "params": {"TARGET_ENV": "https://example.test"},
            },
        )
    assert response.status_code == 200
    assert response.json()["data"]["trigger_type"] == "api_token"


@pytest.mark.asyncio
async def test_idempotent_start_no_double_execute(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    key = str(uuid.uuid4())
    body = {
        **_start_body(
            project_id=project_id,
            env_id=env["id"],
            case_ids=[case["id"]],
            expected_env_version=env["version"],
        ),
        "params": {"TARGET_ENV": "https://example.test"},
    }
    with patch(
        "app.modules.run_orchestration.router.run_test_run_background",
        new_callable=AsyncMock,
    ) as background:
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
    assert first.json()["data"]["receipt"]["id"] == second.json()["data"]["receipt"]["id"]
    assert background.await_count == 1


@pytest.mark.asyncio
async def test_api_080_missing_idempotency_key(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    issued = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["execute"]),
    )
    token = issued.json()["data"]["token"]
    client.cookies.clear()
    response = await client.post(
        "/api/v1/test-runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_id": str(project_id),
            "env_id": env["id"],
            "execution_source": "script",
            "case_ids": [case["id"]],
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_080_read_scope_denied(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    issued = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["read"]),
    )
    token = issued.json()["data"]["token"]
    client.cookies.clear()
    response = await client.post(
        "/api/v1/test-runs",
        headers={
            "Idempotency-Key": str(uuid.uuid4()),
            "Authorization": f"Bearer {token}",
        },
        json={
            "project_id": str(project_id),
            "env_id": env["id"],
            "execution_source": "script",
            "case_ids": [case["id"]],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-003"


@pytest.mark.asyncio
async def test_ac_041_unresolved_func_failed(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(
        client,
        project_id=project_id,
        steps=[{"action": "request", "params": {"method": "GET", "path": "/${uuid()}"}}],
    )
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
    detail = await _poll_run_status(client, start.json()["data"]["id"], wanted={"FAILED"})
    assert detail["status"] == "FAILED"
    summary = detail.get("result_summary") or {}
    assert summary.get("reason") == "variable_unresolved"
    details = summary.get("details") or []
    assert any("function_catalog_unavailable" in str(item) for item in details)
    assert any("${uuid()}" in str(item) for item in details)


@pytest.mark.asyncio
async def test_ac_040_cancel_running_is_stopping_not_cancelled(
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
    now = datetime.now(UTC)
    env_id = uuid.uuid4()
    run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=env_id,
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="RUNNING",
        snapshot={
            "case_ids": [],
            "env_id": str(env_id),
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    await db_session.commit()
    await login_as(client)
    cancel = await client.post(
        f"/api/v1/test-runs/{run.id}/cancel",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": run.aggregate_version},
    )
    assert cancel.status_code == 202
    body = cancel.json()["data"]
    assert body["receipt"]["status"] == "accepted"
    assert body["test_run"]["status"] == "STOPPING"
    assert body["test_run"]["stop_signal_at"]
    detail = await client.get(f"/api/v1/test-runs/{run.id}")
    assert detail.json()["data"]["status"] == "STOPPING"


@pytest.mark.asyncio
async def test_api_210_sse_is_not_command_channel(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    env = await activate_platform_executor_env(client, db_session, seeded_identity)
    case = await create_active_script_case(client, project_id=project_id)
    await login_as(client)
    with patch(
        "app.modules.run_orchestration.router.run_test_run_background",
        new_callable=AsyncMock,
    ):
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
    run_id = start.json()["data"]["id"]

    async def _one_event(*_args: object, **_kwargs: object) -> object:
        yield {
            "event": "progress",
            "data": '{"type":"progress","hint":"pending","progress_percent":10}',
        }

    with patch(
        "app.modules.run_orchestration.router._test_run_sse_events",
        new=_one_event,
    ):
        async with client.stream("GET", f"/api/v1/test-runs/{run_id}/events") as events:
            assert events.status_code == 200
            assert "text/event-stream" in events.headers.get("content-type", "")
            body = ""
            async for line in events.aiter_lines():
                body += line + "\n"
            assert "event:" in body
            assert "command" not in body
    detail = await client.get(f"/api/v1/test-runs/{run_id}")
    assert detail.json()["data"]["status"] == "PENDING"
