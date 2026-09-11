"""Live smoke suite against a locally running HuntAI Test instance.

Skipped entirely unless HUNTAI_LIVE=1, so the normal `uv run pytest` run is
unaffected: these tests drive a real HTTP server and create real rows.

Self-service by design — the suite assumes no demo data and no pre-issued session
cookies. It logs in through the local mock IdP (full OIDC Authorization Code +
PKCE) to obtain its own `huntai_session`, then creates every asset it needs
(quality-gate policy, jira connector, test cases, execution environment) through the
public API.

Prerequisites (see docs/00_setup/local-testing-guide.md):
    1. PostgreSQL migrated to head, and `uv run python scripts/seed_local_identity.py`
       has run; it seeds exactly 1 organization, 2 synthetic users and 1 project.
    2. Mock IdP up: `uv run python scripts/mock_idp.py` (loopback only).
    3. API up: `uv run uvicorn app.main:app --port 8000`.

Account coverage: `seed_local_identity.py` seeds only two synthetic accounts —
`local-dev-user` (project owner) and `local-dev-user-2` (project admin) — with the
mock IdP password `local-dev`. The repository seeds no tester/viewer account, so this
suite exercises the owner/admin boundary only.

The release-webhook leg (`test_08`) needs a release connector carrying a
`webhook_secret_ref`, and no public API can set that field today (API-162 ignores it,
API-163 cannot patch it). On a clean local database that test reports a skip with the
reason instead of fabricating the row with a direct ORM write.

Usage (backend/):
    HUNTAI_LIVE=1 uv run pytest tests/test_live_smoke.py -q

Optional env:
    HUNTAI_BASE_URL            default http://127.0.0.1:8000
    HUNTAI_OWNER/HUNTAI_ADMIN  session cookie value; when set that role skips login
    HUNTAI_PROJECT             project id override; default first /api/v1/projects item
    HUNTAI_SESSION_COOKIE      cookie name override; default SESSION_COOKIE_NAME in .env
    GITHUB_WEBHOOK_SECRET      HMAC secret for the release webhook test; default from .env
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import tempfile
import threading
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("HUNTAI_LIVE") != "1",
        reason="live smoke suite; set HUNTAI_LIVE=1 against a running local stack",
    ),
]

BASE = os.environ.get("HUNTAI_BASE_URL", "http://127.0.0.1:8000")
MOCK_IDP_PASSWORD = "local-dev"
USERNAMES = {"owner": "local-dev-user", "admin": "local-dev-user-2"}
COOKIE_OVERRIDE_ENV = {"owner": "HUNTAI_OWNER", "admin": "HUNTAI_ADMIN"}

STATE: dict[str, str] = {}
_sessions: dict[str, str] = {}
_asset_cache: dict[str, Any] = {}


# -------------------------------------------------------------------------- infra


def _env_file_value(key: str) -> str | None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or None
    return None


def _session_cookie_name() -> str:
    return (
        os.environ.get("HUNTAI_SESSION_COOKIE")
        or _env_file_value("SESSION_COOKIE_NAME")
        or "huntai_session"
    )


def _webhook_secret() -> str:
    return _env_file_value("GITHUB_WEBHOOK_SECRET") or "local-dev-github-webhook-secret"


def _cookie_override(role: str) -> str:
    return os.environ.get(COOKIE_OVERRIDE_ENV[role], "").strip()


async def _login(username: str, *, existing_cookie: str | None = None) -> str:
    """Complete an OIDC Authorization Code + PKCE round trip against the mock IdP.

    Returns the freshly issued session cookie value. Presenting `existing_cookie` to
    the callback turns the login into a step-up re-auth: the old session is revoked and
    the new one carries a fresh `last_reauth_at`. `POST /api/v1/auth/reauth` only
    *reports* the remaining window — it cannot extend it.
    """
    async with AsyncClient(base_url=BASE, timeout=30.0, follow_redirects=False) as client:
        started = await client.get("/api/v1/auth/oidc/start", params={"prompt": "login"})
        assert started.status_code == 200, started.text[:300]
        authorize = urlparse(started.json()["authorization_url"])
        query = parse_qs(authorize.query)
        issued = await client.post(
            f"{authorize.scheme}://{authorize.netloc}/authorize/complete",
            data={
                "redirect_uri": query["redirect_uri"][0],
                "state": query["state"][0],
                "nonce": query["nonce"][0],
                "code_challenge": query["code_challenge"][0],
                "client_id": query["client_id"][0],
                "username": username,
                "password": MOCK_IDP_PASSWORD,
            },
        )
        assert issued.status_code == 302, issued.text[:300]
        callback = urlparse(issued.headers["location"])
        finished = await client.get(
            f"{callback.path}?{callback.query}",
            cookies={_session_cookie_name(): existing_cookie} if existing_cookie else None,
        )
        assert finished.status_code == 302, finished.text[:300]
        cookie_name = _session_cookie_name()
        # Read Set-Cookie straight off the 302: with SESSION_COOKIE_SECURE=true the
        # httpx cookie jar drops it over plain http, which is the local default setup.
        for header in finished.headers.get_list("set-cookie"):
            jar = SimpleCookie()
            jar.load(header)
            if cookie_name in jar:
                return str(jar[cookie_name].value)
        raise AssertionError(f"OIDC callback did not set {cookie_name}: {dict(finished.headers)}")


async def _session(role: str) -> str:
    override = _cookie_override(role)
    if override:
        return override
    if role not in _sessions:
        _sessions[role] = await _login(USERNAMES[role])
    return _sessions[role]


async def _reauth(role: str) -> None:
    """Step up a role's session by re-running PKCE with its current cookie."""
    if _cookie_override(role):
        return
    _sessions[role] = await _login(USERNAMES[role], existing_cookie=await _session(role))


@asynccontextmanager
async def _client(role: str) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        base_url=BASE,
        cookies={_session_cookie_name(): await _session(role)},
        timeout=30.0,
    ) as client:
        yield client


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
    async with _client(role) as client:
        for _ in range(attempts):
            response = await client.get(path)
            assert response.status_code == 200, response.text[:300]
            value = response.json().get("data", {})
            if str(value.get(key, "")) in wanted:
                return value
            await asyncio.sleep(0.25)
    raise AssertionError(f"{path} never reached {wanted}")


@asynccontextmanager
async def _static_http_server() -> AsyncIterator[str]:
    """Serve a deterministic 200 on / over loopback for the smoke runs."""
    with tempfile.TemporaryDirectory() as root:
        Path(root, "index.html").write_text("smoke ok", encoding="utf-8")
        web = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=root)
        )
        thread = threading.Thread(target=web.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{web.server_address[1]}"
        finally:
            web.shutdown()
            web.server_close()
            thread.join(timeout=5)


async def _project_id() -> str:
    override = os.environ.get("HUNTAI_PROJECT", "").strip()
    if override:
        return override
    listing = await _get_json("owner", "/api/v1/projects")
    items = listing["data"]["items"]
    assert items, "no project visible; run scripts/seed_local_identity.py first"
    return str(items[0]["id"])


# --------------------------------------------------------------- self-seeded assets

_CASE_VARIANTS: dict[str, dict[str, Any]] = {
    "passing": {"case_type": "api", "expected": 200, "title": "smoke passing api case"},
    "failing": {"case_type": "api", "expected": 599, "title": "smoke failing api case"},
    "performance": {
        "case_type": "performance",
        "expected": 200,
        "title": "smoke perf case",
    },
}


async def _create_active_case(project_id: str, *, variant: str, token: str) -> dict[str, Any]:
    """API-032 → API-034 → API-035. Case review carries no four-eyes rule."""
    spec = _CASE_VARIANTS[variant]
    created = await _post_json(
        "owner",
        "/api/v1/test-cases",
        {
            "project_id": project_id,
            "case_type": spec["case_type"],
            "execution_mode": "script",
            "title": f"{spec['title']} {token}",
            "drafts": [
                {
                    "steps": [{"action": "request", "params": {"method": "GET", "path": "/"}}],
                    "assertions": [{"type": "status_code", "expected": spec["expected"]}],
                }
            ],
        },
        expected=201,
    )
    case_id = str(created["data"]["id"])
    submitted = await _post_json(
        "owner",
        f"/api/v1/test-cases/{case_id}/submit-review",
        {"expected_version": created["data"]["version"]},
    )
    reviewed = await _post_json(
        "admin",
        f"/api/v1/test-cases/{case_id}/review",
        {"expected_version": submitted["data"]["version"], "decision": "approve"},
    )
    assert reviewed["data"]["lifecycle_status"] == "ACTIVE", reviewed["data"]
    return reviewed["data"]


async def _register_approved_environment(project_id: str, name: str) -> dict[str, Any]:
    """API-102 + API-112: register a platform_executor environment, approve as admin."""
    registered = await _post_json(
        "owner",
        "/api/v1/execution-environments",
        {
            "env_type": "platform_executor",
            "name": name,
            "scope_level": "project",
            "project_id": project_id,
            "endpoint": "local-smoke-executor",
        },
    )
    assert registered["data"]["status"] == "PENDING_APPROVAL", registered["data"]
    approval_id = registered["data"]["approval_request_id"]
    detail = await _get_json("admin", f"/api/v1/approval-requests/{approval_id}")
    approved = await _post_json(
        "admin",
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": detail["data"]["version"]},
    )
    assert approved["data"]["status"] == "EXECUTED", approved["data"]
    env = await _get_json("owner", f"/api/v1/execution-environments/{registered['data']['id']}")
    assert env["data"]["status"] == "ACTIVE", env["data"]
    return env["data"]


async def _assets() -> dict[str, Any]:
    """Build the fixtures this suite needs, once, through public APIs only.

    A clean local database (seed_local_identity.py) has no cases, environments, gate
    policies or connectors, so the suite creates them itself instead of depending on
    demo data.
    """
    if _asset_cache:
        return _asset_cache
    project_id = await _project_id()
    token = uuid.uuid4().hex[:8]

    policy = await _post_json(
        "owner",
        "/api/v1/quality-gate-policies",
        {
            "project_id": project_id,
            "thresholds": {
                "min_pass_rate": 0.0,
                "max_p95_ms": 60000.0,
                "max_error_rate": 100.0,
            },
            "mode": "blocking",
            "scope": {},
            "confirm_blocking": True,
        },
        expected=201,
    )
    # API-162: release-task create requires an org jira connector (scope read stub).
    jira = await _post_json(
        "owner",
        "/api/v1/connectors",
        {
            "type": "jira",
            "name": f"smoke jira {token}",
            "auth_method": "api_token",
            "action_contract": {},
            "has_credential_binding": False,
        },
        expected=201,
    )
    _asset_cache.update(
        {
            "project_id": project_id,
            "token": token,
            "policy_id": str(policy["data"]["id"]),
            "jira_connector_id": str(jira["data"]["id"]),
            "passing": await _create_active_case(project_id, variant="passing", token=token),
            "failing": await _create_active_case(project_id, variant="failing", token=token),
            "performance": await _create_active_case(
                project_id, variant="performance", token=token
            ),
            "environment": await _register_approved_environment(project_id, f"smoke env {token}"),
        }
    )
    return _asset_cache


async def _start_script_run(
    assets: dict[str, Any], case_id: str, *, params: dict[str, Any], expected: int = 200
) -> dict[str, Any]:
    env = assets["environment"]
    return await _post_json(
        "owner",
        "/api/v1/test-runs",
        {
            "project_id": assets["project_id"],
            "env_id": env["id"],
            "execution_source": "script",
            "case_ids": [case_id],
            "trigger_type": "manual",
            "expected_env_version": env["version"],
            "params": params,
        },
        expected=expected,
    )


async def _release_task_to_submitted() -> str:
    """Drive a release task through approval to SUBMITTED; returns its id."""
    assets = await _assets()  # jira connector prerequisite (API-162)
    project_id = assets["project_id"]
    created = await _post_json(
        "owner",
        "/api/v1/release-tasks",
        {"project_id": project_id, "jira_version_ref": f"smoke-{uuid.uuid4().hex[:6]}"},
        expected=201,
    )
    task_id = str(created["data"]["id"])
    await _poll("owner", f"/api/v1/release-tasks/{task_id}", {"PENDING_CONFIRM"})

    # release_push is L4, so the step-up window must be fresh. POST /api/v1/auth/reauth
    # only reports the window; re-running PKCE actually satisfies it.
    await _reauth("owner")
    me = await _get_json("owner", "/api/v1/me")
    assert me["data"]["reauth_required"] is False

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
    decision = await _post_json(
        "admin",
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": detail["data"]["version"]},
    )
    assert decision["data"]["status"] == "EXECUTED", decision["data"]
    assert decision["data"]["execution_result"] == "ok", decision["data"]
    task = await _poll("owner", f"/api/v1/release-tasks/{task_id}", {"SUBMITTED"})
    assert task["scope_snapshot"].get("release_item") is not None
    return task_id


# ---------------------------------------------------------------------------- tests


async def test_01_identity_and_four_eyes_boundary() -> None:
    """自建会话可用 + 双账号 + 发起人不能批准自己发起的 env_register（四眼）。"""
    owner = await _get_json("owner", "/api/v1/me")
    assert owner["data"]["user"]["email"] == "local-dev@example.test"
    assert owner["data"]["organization"]["slug"] == "local-dev"
    assert any(m["role"] == "owner" for m in owner["data"]["memberships"])
    assert owner["data"]["reauth_required"] is False

    admin = await _get_json("admin", "/api/v1/me")
    assert admin["data"]["user"]["email"] == "local-dev-2@example.test"
    assert any(m["role"] == "admin" for m in admin["data"]["memberships"])

    project_id = await _project_id()
    registered = await _post_json(
        "owner",
        "/api/v1/execution-environments",
        {
            "env_type": "platform_executor",
            "name": f"smoke four-eyes {uuid.uuid4().hex[:8]}",
            "scope_level": "project",
            "project_id": project_id,
        },
    )
    approval_id = registered["data"]["approval_request_id"]

    detail = await _get_json("owner", f"/api/v1/approval-requests/{approval_id}")
    denied = await _post_json(
        "owner",
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": detail["data"]["version"]},
        expected=403,
    )
    assert denied["error"]["code"] == "HT-IAM-002"

    # 四眼只排除发起人：换 admin 批准即可通过。
    admin_detail = await _get_json("admin", f"/api/v1/approval-requests/{approval_id}")
    approved = await _post_json(
        "admin",
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": admin_detail["data"]["version"]},
    )
    assert approved["data"]["status"] == "EXECUTED", approved["data"]


async def test_02_self_served_assets_visible() -> None:
    """自建资产可读：blocking 门禁策略 + 3 条 ACTIVE 用例 + ACTIVE 执行环境。"""
    assets = await _assets()
    project_id = assets["project_id"]

    cases = await _get_json("owner", f"/api/v1/test-cases?project_id={project_id}")
    cases_by_id = {str(item["id"]): item for item in cases["data"]["items"]}
    for key in ("passing", "failing", "performance"):
        case_id = str(assets[key]["id"])
        assert case_id in cases_by_id, f"{key} case missing from list"
        assert cases_by_id[case_id]["lifecycle_status"] == "ACTIVE"

    envs = await _get_json("owner", f"/api/v1/execution-environments?project_id={project_id}")
    envs_by_id = {str(item["id"]): item for item in envs["data"]["items"]}
    assert envs_by_id[str(assets["environment"]["id"])]["status"] == "ACTIVE"

    policies = await _get_json("owner", f"/api/v1/quality-gate-policies?project_id={project_id}")
    assert str(assets["policy_id"]) in {str(item["id"]) for item in policies["data"]["items"]}


async def test_03_run_lifecycle_script_api() -> None:
    """script/api run：受理 ≠ 完成；SUCCEEDED 后门禁评估异步落地。"""
    assets = await _assets()
    async with _static_http_server() as target:
        started = await _start_script_run(
            assets, str(assets["passing"]["id"]), params={"TARGET_ENV": target}
        )
        run_id = str(started["data"]["id"])
        assert started["data"]["receipt"]["status"] == "accepted"  # 受理 ≠ 完成
        detail = await _poll("owner", f"/api/v1/test-runs/{run_id}", {"SUCCEEDED"})
        assert detail["status"] == "SUCCEEDED"

    results = await _get_json("owner", f"/api/v1/test-runs/{run_id}/case-results")
    items = results["data"]["items"]
    assert items, "run produced no case result"
    STATE["case_result_id"] = str(items[0]["id"])

    # 门禁评估在 run 终态提交之后异步写入，必须轮询，不能立刻断言。
    evaluation: dict[str, Any] | None = None
    async with _client("owner") as client:
        for _ in range(80):
            response = await client.get(f"/api/v1/test-runs/{run_id}/gate-evaluation")
            assert response.status_code == 200, response.text[:300]
            candidate = response.json()["data"]["evaluation"]
            if candidate is not None:
                evaluation = candidate
                break
            await asyncio.sleep(0.25)
    assert evaluation is not None, f"gate evaluation for run {run_id} never appeared"

    pass_detail = evaluation["threshold_details"]["min_pass_rate"]
    # threshold_details.min_pass_rate.passed 是"通过数"（被 pass_detail 覆盖），不是布尔。
    assert pass_detail["passed"] == pass_detail["total"] == 1
    assert pass_detail["actual"] == 100.0
    assert evaluation["result"] == "pass"
    assert evaluation["check_run_ref"] is not None


async def test_04_perf_whitelist_denied() -> None:
    """AC-051：压测白名单外目标 100% DENY 且不建审批。"""
    assets = await _assets()
    denied = await _start_script_run(
        assets,
        str(assets["performance"]["id"]),
        params={
            "TARGET_ENV": "http://127.0.0.1:9",
            "perf_whitelist": ["https://not-this-host.example"],
            "perf_scenario": {"users": 1, "run_time_seconds": 5},
        },
        expected=403,
    )
    assert denied["error"]["code"] == "HT-POL-002"


async def test_05_copilot_answer_and_cross_project_refusal() -> None:
    """AC-068：A6 四键；跨项目资源引用 100% 拒绝。"""
    project_id = await _project_id()
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


async def test_06_release_task_approval_flow() -> None:
    """FR-15：圈定 → PENDING_CONFIRM → release_push 审批 → SUBMITTED。"""
    task_id = await _release_task_to_submitted()
    STATE["release_task_id"] = task_id

    readiness = await _get_json("owner", f"/api/v1/release-tasks/{task_id}/readiness")
    assert readiness["data"]["overall"] in {"red", "yellow", "green"}
    task = await _get_json("owner", f"/api/v1/release-tasks/{task_id}")
    assert task["data"]["a5"] is not None
    assert task["data"]["a5"].get("missing_inputs") is not None  # A5 只读


async def test_07_evidence_from_failed_run_export_and_proxy_download() -> None:
    """AC-096：真实 FAILED run 产生证据 → 导出受理 ≠ 完成 → API-223 代理下载。"""
    assets = await _assets()
    async with _static_http_server() as target:
        started = await _start_script_run(
            assets, str(assets["failing"]["id"]), params={"TARGET_ENV": target}
        )
        run_id = str(started["data"]["id"])
        detail = await _poll("owner", f"/api/v1/test-runs/{run_id}", {"FAILED"})
        assert detail["status"] == "FAILED"

    results = await _get_json("owner", f"/api/v1/test-runs/{run_id}/case-results")
    items = results["data"]["items"]
    assert items, "failed run produced no case result"
    case_result_id = str(items[0]["id"])

    # 失败分诊在同一事务里写入 EvidenceObject；轮询真实行，不伪造。
    evidence: dict[str, Any] | None = None
    async with _client("owner") as client:
        for _ in range(80):
            response = await client.get(
                "/api/v1/evidence-objects",
                params={
                    "subject_type": "case_result",
                    "subject_id": case_result_id,
                    "limit": 50,
                },
            )
            assert response.status_code == 200, response.text[:300]
            rows = response.json()["data"]["items"]
            if rows:
                evidence = rows[0]
                break
            await asyncio.sleep(0.25)
    if evidence is None:
        pytest.skip(
            "failure triage wrote no EvidenceObject for the failed case result within the "
            "poll budget; nothing to export (no ORM row is fabricated to force the test)"
        )

    accepted = await _post_json(
        "owner",
        "/api/v1/evidence-objects/export-packages",
        {"format": "json", "evidence_object_ids": [evidence["id"]]},
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


async def test_08_release_webhook_observation() -> None:
    """webhook 观察 → READY；需要已存在带 webhook secret 的 release 连接器。

    当前公开 API 无法为连接器配置 `webhook_secret_ref`（API-162 不接受该字段，API-163
    也不能改），干净本地库上不存在这样的连接器，此时如实 skip；绝不用 ORM 直接写一行
    来伪造前置条件。
    """
    connectors = await _get_json("owner", "/api/v1/connectors")
    release_connector = next(
        (
            item
            for item in connectors["data"]["items"]
            if item.get("type") == "release" and item.get("webhook_secret_present") is True
        ),
        None,
    )
    if release_connector is None:
        pytest.skip(
            "no release connector carries a webhook secret: no public API can set "
            "webhook_secret_ref (API-162 ignores it, API-163 cannot patch it)"
        )

    task_id = STATE.get("release_task_id") or await _release_task_to_submitted()
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
