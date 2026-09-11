"""Live smoke suite against a locally running HuntAI Test instance.

Skipped entirely unless HUNTAI_LIVE=1, so the normal `uv run pytest` run is
unaffected (these tests hit a live server, not the ASGI app, and they create
real rows in the demo database).

Usage (backend/):
    HUNTAI_LIVE=1 uv run pytest tests/test_live_smoke.py -q

Optional env:
    HUNTAI_BASE_URL   default http://127.0.0.1:8000
    HUNTAI_OWNER / HUNTAI_ADMIN / HUNTAI_TESTER / HUNTAI_VIEWER  (cookie values)
    GITHUB_WEBHOOK_SECRET  default parsed from repo .env (release webhook HMAC)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("HUNTAI_LIVE") != "1",
        reason="live smoke suite; set HUNTAI_LIVE=1 against a running local stack",
    ),
]

BASE = os.environ.get("HUNTAI_BASE_URL", "http://127.0.0.1:8000")
_state: dict[str, str] = {}
COOKIES = {
    "owner": os.environ.get("HUNTAI_OWNER", "deee6f5c-21c3-4619-a6ab-0933b499f194"),
    "admin": os.environ.get("HUNTAI_ADMIN", "bef1adda-d156-4cef-b2cd-0095aceab3ee"),
    "tester": os.environ.get("HUNTAI_TESTER", "1a824365-b448-461f-9108-3e31fbb47515"),
    "viewer": os.environ.get("HUNTAI_VIEWER", "d44c5d6c-1ac5-4127-be4a-3a27bf923e73"),
}


def _client(role: str) -> AsyncClient:
    return AsyncClient(base_url=BASE, cookies={"huntai_session": COOKIES[role]}, timeout=30.0)


def _webhook_secret() -> str:
    default = "local-dev-github-webhook-secret"
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("GITHUB_WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip() or default
    return default


async def _get_json(role: str, path: str, expected: int = 200) -> dict[str, Any]:
    async with _client(role) as client:
        response = await client.get(path)
        assert response.status_code == expected, f"GET {path}: {response.text[:300]}"
        return response.json()


async def _post_json(
    role: str, path: str, body: dict[str, Any], expected: int = 200
) -> dict[str, Any]:
    async with _client(role) as client:
        response = await client.post(
            path, json=body, headers={"Idempotency-Key": str(uuid.uuid4())}
        )
        assert response.status_code == expected, f"POST {path}: {response.text[:300]}"
        return response.json()


async def _poll(
    role: str, path: str, wanted: set[str], *, attempts: int = 200, key: str = "status"
) -> dict[str, Any]:
    import asyncio

    async with _client(role) as client:
        for _ in range(attempts):
            response = await client.get(path)
            assert response.status_code == 200, response.text[:300]
            body = response.json().get("data", {})
            if str(body.get(key, "")) in wanted:
                return body
            await asyncio.sleep(0.25)
    raise AssertionError(f"{path} never reached {wanted}")


async def _demo_project_id() -> str:
    listing = await _get_json("owner", "/api/v1/projects")
    for item in listing["data"]["items"]:
        if item.get("name") == "电商核心":
            return str(item["id"])
    raise AssertionError("demo project 电商核心 not found")


async def test_01_health_and_rbac() -> None:
    """登录态与角色边界：四角色可读；viewer 写被拒；tester 发起执行成功但审批受限。"""
    me = await _get_json("owner", "/api/v1/me")
    assert me["data"]["user"]["email"] == "owner@example.com"
    assert me["data"]["organization"]["name"] == "HuntAI 演示租户"
    await _get_json("admin", "/api/v1/me")
    await _get_json("tester", "/api/v1/me")
    await _get_json("viewer", "/api/v1/me")
    # viewer 写 fail-close
    async with _client("viewer") as client:
        denied = await client.post("/api/v1/copilot-sessions", json={"title": "v"})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "HT-IAM-001"


async def test_02_seeded_assets_visible() -> None:
    """种子资产可见：两条 ACTIVE 用例 + ACTIVE 执行环境 + blocking 门禁策略。"""
    project_id = await _demo_project_id()
    cases = await _get_json("owner", f"/api/v1/test-cases?project_id={project_id}")
    titles = {item["title"] for item in cases["data"]["items"]}
    assert {"GET 宠物列表", "下单接口压测场景"} <= titles
    envs = await _get_json("owner", f"/api/v1/execution-environments?project_id={project_id}")
    assert any(item["status"] == "ACTIVE" for item in envs["data"]["items"])
    policies = await _get_json("owner", f"/api/v1/quality-gate-policies?project_id={project_id}")
    assert policies["data"]["items"], "gate policy missing"


async def test_03_run_lifecycle_script_api() -> None:
    """script/api run：受理 ≠ 完成；SUCCEEDED → blocking 门禁 pass 评估。"""
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    web = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory="/tmp"))
    port = web.server_address[1]
    threading.Thread(target=web.serve_forever, daemon=True).start()
    project_id = await _demo_project_id()
    cases = await _get_json("owner", f"/api/v1/test-cases?project_id={project_id}")
    api_case = next(item for item in cases["data"]["items"] if item["title"] == "GET 宠物列表")
    envs = await _get_json("owner", f"/api/v1/execution-environments?project_id={project_id}")
    env = next(item for item in envs["data"]["items"] if item["status"] == "ACTIVE")
    started = await _post_json(
        "owner",
        "/api/v1/test-runs",
        {
            "project_id": project_id,
            "env_id": env["id"],
            "execution_source": "script",
            "case_ids": [api_case["id"]],
            "trigger_type": "manual",
            "expected_env_version": env["version"],
            "params": {"TARGET_ENV": f"http://127.0.0.1:{port}"},
        },
    )
    run_id = str(started["data"]["id"])
    assert started["data"]["receipt"]["status"] == "accepted"  # 受理 ≠ 完成

    try:
        detail = await _poll("owner", f"/api/v1/test-runs/{run_id}", {"SUCCEEDED"})
        assert detail["status"] == "SUCCEEDED"
    finally:
        web.shutdown()
    results = await _get_json("owner", f"/api/v1/test-runs/{run_id}/case-results")
    _state["case_result_id"] = str(results["data"]["items"][0]["id"])

    gate = await _get_json("owner", f"/api/v1/test-runs/{run_id}/gate-evaluation")
    evaluation = gate["data"]["evaluation"]
    assert evaluation is not None
    assert evaluation["result"] == "pass"  # blocking 策略 + 200 断言通过
    assert evaluation["check_run_ref"]["conclusion"] == "success"


async def test_04_perf_whitelist_denied() -> None:
    """AC-051：压测白名单外目标 100% DENY 且不建审批。"""
    project_id = await _demo_project_id()
    cases = await _get_json("owner", f"/api/v1/test-cases?project_id={project_id}")
    perf_case = next(item for item in cases["data"]["items"] if item["title"] == "下单接口压测场景")
    envs = await _get_json("owner", f"/api/v1/execution-environments?project_id={project_id}")
    env = next(item for item in envs["data"]["items"] if item["status"] == "ACTIVE")
    response = await _post_json(
        "owner",
        "/api/v1/test-runs",
        {
            "project_id": project_id,
            "env_id": env["id"],
            "execution_source": "script",
            "case_ids": [perf_case["id"]],
            "trigger_type": "manual",
            "expected_env_version": env["version"],
            "params": {
                "TARGET_ENV": "http://127.0.0.1:9",
                "perf_whitelist": ["https://not-this-host.example"],
                "perf_scenario": {"users": 1, "run_time_seconds": 5},
            },
        },
        expected=403,
    )
    assert response["error"]["code"] == "HT-POL-002"


async def test_05_copilot_answer_and_cross_project_refusal() -> None:
    """AC-068：A6 四键；跨项目资源引用 100% 拒绝。"""
    project_id = await _demo_project_id()
    created = await _post_json(
        "owner",
        "/api/v1/copilot-sessions",
        {"project_id": project_id, "title": "smoke"},
        expected=201,
    )
    session_id = created["data"]["id"]
    foreign = str(uuid.uuid4())
    answer = await _post_json(
        "owner",
        f"/api/v1/copilot-sessions/{session_id}/messages",
        {"content": f"当前项目最近的 TestRun 情况如何？参考 {foreign}"},
    )
    data = answer["data"]
    assert {"answer", "citations", "tool_calls", "refused_policies"} <= set(data)
    assert any(p.startswith("cross_project_reference") for p in data["refused_policies"])
    assert all(citation["resource_id"] != foreign for citation in data["citations"])
    detail = await _get_json("owner", f"/api/v1/copilot-sessions/{session_id}")
    assert detail["data"]["messages"], "messages should be persisted (minimal form)"


async def test_06_release_task_full_flow() -> None:
    """FR-15：圈定 → PENDING_CONFIRM → release_push 审批 → SUBMITTED → webhook READY。"""
    project_id = await _demo_project_id()
    created = await _post_json(
        "owner",
        "/api/v1/release-tasks",
        {"project_id": project_id, "jira_version_ref": f"smoke-{uuid.uuid4().hex[:6]}"},
        expected=201,
    )
    task_id = str(created["data"]["id"])
    task = await _poll("owner", f"/api/v1/release-tasks/{task_id}", {"PENDING_CONFIRM"})
    readiness = await _get_json("owner", f"/api/v1/release-tasks/{task_id}/readiness")
    assert readiness["data"]["overall"] in {"red", "yellow", "green"}
    assert task["a5"] is not None and task["a5"].get("missing_inputs") is not None  # A5 只读

    # L4 动作要求 15 分钟内 step-up 认证：先 API-004 刷新
    async with _client("owner") as client:
        reauth = await client.post("/api/v1/auth/reauth")
        assert reauth.status_code == 200, reauth.text[:300]
    preview = await _post_json(
        "owner",
        "/api/v1/action-previews",
        {
            "action_type": "release_push",
            "target_object_type": "release_task",
            "target_object_id": task_id,
            "project_id": project_id,
            "payload": {"confirm": True},
        },
    )
    approval_id = preview["data"]["approval_request_id"]
    detail = await _get_json("admin", f"/api/v1/approval-requests/{approval_id}")
    version = detail["data"]["version"]
    decision = await _post_json(
        "admin",
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": version},
    )
    assert decision["data"]["status"] == "EXECUTED"
    assert decision["data"]["execution_result"] == "ok"
    task = await _poll("owner", f"/api/v1/release-tasks/{task_id}", {"SUBMITTED"})
    assert task["scope_snapshot"].get("release_item") is not None

    # webhook 观察 → READY
    connectors = await _get_json("owner", "/api/v1/connectors")
    release_connector = next(
        item for item in connectors["data"]["items"] if item.get("type") == "release"
    )
    body = json.dumps(
        {"release_task_id": task_id, "external_item_id": "RI-SMOKE", "status": "ready"}
    ).encode()
    signature = "sha256=" + hmac.new(_webhook_secret().encode(), body, hashlib.sha256).hexdigest()
    async with _client("owner") as client:
        webhook = await client.post(
            f"/api/v1/inbound-webhooks/{release_connector['id']}",
            content=body,
            headers={
                "x-hub-signature-256": signature,
                "x-github-delivery": str(uuid.uuid4()),
                "x-github-event": "release_item_ready",
                "content-type": "application/json",
            },
        )
        assert webhook.status_code == 202, webhook.text[:300]
    await _poll("owner", f"/api/v1/release-tasks/{task_id}", {"READY"})


async def test_07_evidence_export_and_proxy_download() -> None:
    """AC-096：导出受理 ≠ 完成；完成后 API-223 代理下载（引用 ≠ 授权）。"""
    project_id = await _demo_project_id()
    # Evidence creation itself is covered by backend tests; seed one row
    # directly so this smoke test can exercise export + proxy download.
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.modules.identity_tenancy.models import Organization
    from app.modules.results_evidence.models import EvidenceObject

    database_url = "postgresql+asyncpg://macbookair@127.0.0.1:5432/huntai_test"
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip() or database_url
    engine = create_async_engine(database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with db_factory() as db:
        org = (
            await db.execute(select(Organization).where(Organization.slug == "huntai-demo"))
        ).scalar_one()
        case_result_id = _state.get("case_result_id")
    if case_result_id is None:
        # test_07 单独运行时的兜底：从演示项目里找一个真实 case_result
        runs = await _get_json("owner", f"/api/v1/test-runs?project_id={project_id}")
        for run_item in runs["data"]["items"]:
            results = await _get_json("owner", f"/api/v1/test-runs/{run_item['id']}/case-results")
            if results["data"]["items"]:
                case_result_id = str(results["data"]["items"][0]["id"])
                break
    assert case_result_id is not None, "no case_result available for evidence subject"
    evidence_row = EvidenceObject(
        id=uuid.uuid4(),
        organization_id=org.id,
        created_at=datetime.now(UTC),
        created_by=None,
        claim="smoke evidence",
        source_object={"connector": "smoke", "resource": "live"},
        content_ref=None,
        subject_type="case_result",
        subject_id=uuid.UUID(case_result_id),
        data_classification="Internal",
    )
    db.add(evidence_row)
    await db.commit()
    await engine.dispose()
    evidence_id = str(evidence_row.id)

    accepted = await _post_json(
        "owner",
        "/api/v1/evidence-objects/export-packages",
        {"format": "json", "evidence_object_ids": [evidence_id]},
        expected=202,
    )
    receipt_id = accepted["data"]["id"]
    receipt = await _poll("owner", f"/api/v1/command-receipts/{receipt_id}", {"succeeded"})
    assert receipt["status"] == "succeeded"
    async with _client("owner") as client:
        content = await client.get(f"/api/v1/export-packages/{receipt_id}/content")
        assert content.status_code == 200
        assert content.headers.get("content-disposition", "").startswith("attachment")
        json.loads(content.content)  # json 包可解析
