"""ASGI tests for local integration mocks (no real TCP)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

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

SECRET_PATTERN = re.compile(
    r"(secret|password|token|credential|authorization)",
    re.IGNORECASE,
)


def _assert_no_secrets(payload: Any) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert not SECRET_PATTERN.search(str(key))
            _assert_no_secrets(value)
    elif isinstance(payload, list):
        for item in payload:
            _assert_no_secrets(item)
    elif isinstance(payload, str):
        assert "test-github-webhook-secret" not in payload
        assert "test-jenkins-api-token" not in payload


@pytest.fixture
async def mock_client() -> AsyncClient:
    mock_integrations.reset_state()
    transport = ASGITransport(app=mock_integrations.app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8091") as client:
        yield client


@pytest.mark.asyncio
async def test_healthz(mock_client: AsyncClient) -> None:
    response = await mock_client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok"}
    _assert_no_secrets(payload)


@pytest.mark.asyncio
async def test_jira_create_issue_idempotent(mock_client: AsyncClient) -> None:
    body = {
        "fields": {
            "project": {"key": "HT"},
            "summary": "Demo issue",
            "description": "Created by mock",
        }
    }
    headers = {"X-External-Request-Id": "req-001"}
    first = await mock_client.post("/jira/rest/api/2/issue", json=body, headers=headers)
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["key"].startswith("HT-")
    _assert_no_secrets(first_payload)

    second = await mock_client.post("/jira/rest/api/2/issue", json=body, headers=headers)
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload["key"] == first_payload["key"]
    assert second_payload["id"] == first_payload["id"]

    fetched = await mock_client.get(f"/jira/rest/api/2/issue/{first_payload['key']}")
    assert fetched.status_code == 200
    _assert_no_secrets(fetched.json())


@pytest.mark.asyncio
async def test_github_check_run_phases(mock_client: AsyncClient) -> None:
    created = await mock_client.post("/github/repos/acme/demo/check-runs", json={})
    assert created.status_code == 201
    created_payload = created.json()
    assert created_payload["status"] == "queued"
    assert created_payload["conclusion"] is None
    check_id = created_payload["id"]
    _assert_no_secrets(created_payload)

    in_progress = await mock_client.patch(
        f"/github/repos/acme/demo/check-runs/{check_id}",
        json={"status": "in_progress"},
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"

    completed = await mock_client.patch(
        f"/github/repos/acme/demo/check-runs/{check_id}",
        json={"status": "completed", "conclusion": "failure"},
    )
    assert completed.status_code == 200
    done_payload = completed.json()
    assert done_payload["status"] == "completed"
    assert done_payload["conclusion"] == "failure"
    _assert_no_secrets(done_payload)


@pytest.mark.asyncio
async def test_jenkins_flow(mock_client: AsyncClient) -> None:
    auth = ("", "local-jenkins-token")
    job = await mock_client.get("/jenkins/job/local-demo/api/json", auth=auth)
    assert job.status_code == 200
    assert job.json()["buildable"] is True

    trigger = await mock_client.post("/jenkins/job/local-demo/build", auth=auth)
    assert trigger.status_code == 201
    location = trigger.headers.get("location")
    assert location is not None
    assert "/jenkins/queue/item/" in location

    queue_id = location.rstrip("/").split("/")[-1]
    queue = await mock_client.get(f"/jenkins/queue/item/{queue_id}/api/json", auth=auth)
    assert queue.status_code == 200
    build_number = queue.json()["executable"]["number"]
    assert isinstance(build_number, int)

    junit = await mock_client.get(
        f"/jenkins/job/local-demo/{build_number}/artifact/junit.xml",
        auth=auth,
    )
    assert junit.status_code == 200
    assert "<failure" in junit.text
    assert 'name="test_passing"' in junit.text

    log = await mock_client.get(
        f"/jenkins/job/local-demo/{build_number}/logText/progressiveText",
        params={"start": 0},
        auth=auth,
    )
    assert log.status_code == 200
    assert log.headers.get("x-text-size") is not None
    assert int(log.headers["x-text-size"]) >= len(log.text)


@pytest.mark.asyncio
async def test_release_item_idempotent(mock_client: AsyncClient) -> None:
    body = {
        "release_task_id": str(uuid.uuid4()),
        "prepare_key": "prepare-key-abc",
    }
    first = await mock_client.post("/release/items", json=body)
    assert first.status_code == 201
    first_payload = first.json()
    assert first_payload["external_system"] == "release_mock"
    assert first_payload["external_item_id"].startswith("RI-")
    _assert_no_secrets(first_payload)

    second = await mock_client.post("/release/items", json=body)
    assert second.status_code == 201
    assert second.json() == first_payload


@pytest.mark.asyncio
async def test_confluence_demo_pages(mock_client: AsyncClient) -> None:
    html = await mock_client.get("/confluence/")
    assert html.status_code == 200
    text = html.text.lower()
    assert "m4" in text
    assert "not a connector" in text
    assert "rag" in text

    openapi = await mock_client.get("/confluence/openapi.json")
    assert openapi.status_code == 200
    spec = openapi.json()
    assert spec["openapi"] == "3.0.3"
    assert spec["info"]["title"] == "Local Demo Orders API"
    _assert_no_secrets(spec)


@pytest.mark.asyncio
async def test_emit_webhook_signs_outbound(mock_client: AsyncClient) -> None:
    outbound = AsyncMock()
    outbound.status_code = 202
    outbound.text = "accepted"

    captured: dict[str, Any] = {}

    async def _fake_post(
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
    ) -> AsyncMock:
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        return outbound

    body = {
        "huntai_base": "http://127.0.0.1:8000",
        "connector_id": str(uuid.uuid4()),
        "event": "release_item_ready",
        "delivery_id": str(uuid.uuid4()),
        "body": {
            "release_task_id": str(uuid.uuid4()),
            "external_item_id": "RI-demo1234",
            "status": "ready",
        },
    }

    with patch("mock_integrations.httpx.AsyncClient") as client_cls:
        client_instance = AsyncMock()
        client_instance.__aenter__.return_value = client_instance
        client_instance.__aexit__.return_value = None
        client_instance.post = _fake_post
        client_cls.return_value = client_instance

        response = await mock_client.post("/dev/emit-webhook", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivered"] is True
    assert payload["status_code"] == 202
    _assert_no_secrets(payload)

    signature = captured["headers"]["x-hub-signature-256"]
    assert signature.startswith("sha256=")
    assert captured["headers"]["x-github-event"] == "release_item_ready"
    assert captured["headers"]["x-github-delivery"] == body["delivery_id"]
    assert json.loads(captured["content"]) == body["body"]


@pytest.mark.asyncio
async def test_emit_webhook_rejects_secrets_in_body(mock_client: AsyncClient) -> None:
    body = {
        "huntai_base": "http://127.0.0.1:8000",
        "connector_id": str(uuid.uuid4()),
        "event": "release_item_ready",
        "delivery_id": str(uuid.uuid4()),
        "webhook_secret": "must-not-accept",
        "body": {"status": "ready"},
    }
    response = await mock_client.post("/dev/emit-webhook", json=body)
    assert response.status_code == 400
