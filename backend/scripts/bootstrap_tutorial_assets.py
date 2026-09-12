"""Create user-ui-guide §2 assets through public APIs (local tutorial close-out).

Does not write rows via ORM/SQL. Idempotent: skips assets that already exist.

Prerequisites: mock IdP (8090), API (8000), seed_local_identity.py.

Usage (from backend/):
    uv run python scripts/bootstrap_tutorial_assets.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from httpx import AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = os.environ.get("HUNTAI_BASE_URL", "http://127.0.0.1:8000")
PROJECT_ID = "00000000-0000-4000-8000-000000000003"
ENV_NAME = "本地教程环境"
PASSWORD = "local-dev"
USERNAMES = {"owner": "local-dev-user", "admin": "local-dev-user-2"}
COOKIE_NAME_DEFAULT = "huntai_session"


def _env_file_value(key: str) -> str | None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or None
    return None


def _cookie_name() -> str:
    return (
        os.environ.get("HUNTAI_SESSION_COOKIE")
        or _env_file_value("SESSION_COOKIE_NAME")
        or COOKIE_NAME_DEFAULT
    )


async def _login(username: str, existing: str | None = None) -> str:
    """OIDC Authorization Code + PKCE against the mock IdP. Isolated per call."""
    async with AsyncClient(base_url=BASE, timeout=30.0, follow_redirects=False) as client:
        started = await client.get("/api/v1/auth/oidc/start", params={"prompt": "login"})
        started.raise_for_status()
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
                "password": PASSWORD,
            },
        )
        if issued.status_code != 302:
            raise SystemExit(
                f"IdP authorize/complete HTTP {issued.status_code}: {issued.text[:300]}"
            )
        callback = urlparse(issued.headers["location"])
        cookies = {_cookie_name(): existing} if existing else None
        finished = await client.get(
            f"{callback.path}?{callback.query}",
            cookies=cookies,
        )
        if finished.status_code != 302:
            raise SystemExit(f"OIDC callback HTTP {finished.status_code}: {finished.text[:300]}")
        name = _cookie_name()
        for header in finished.headers.get_list("set-cookie"):
            jar = SimpleCookie()
            jar.load(header)
            if name in jar:
                return str(jar[name].value)
        raise SystemExit(f"OIDC callback did not set {name}")


async def _get(client: AsyncClient, path: str) -> dict[str, Any]:
    response = await client.get(path)
    if response.status_code != 200:
        raise SystemExit(f"GET {path} HTTP {response.status_code}: {response.text[:400]}")
    return response.json()


async def _post(
    client: AsyncClient, path: str, body: dict[str, Any], *, expected: int = 200
) -> dict[str, Any]:
    response = await client.post(path, json=body, headers={"Idempotency-Key": str(uuid.uuid4())})
    if response.status_code != expected:
        raise SystemExit(f"POST {path} HTTP {response.status_code}: {response.text[:400]}")
    return response.json()


async def _ensure_policy(owner: AsyncClient) -> str:
    listing = await _get(owner, f"/api/v1/quality-gate-policies?project_id={PROJECT_ID}")
    items = listing.get("data", {}).get("items") or []
    if items:
        policy_id = str(items[0]["id"])
        print(f"门禁策略已存在：{policy_id}")
        return policy_id
    created = await _post(
        owner,
        "/api/v1/quality-gate-policies",
        {
            "project_id": PROJECT_ID,
            "thresholds": {
                "min_pass_rate": 95,
                "max_p95_ms": 500,
                "max_error_rate": 1,
            },
            "mode": "report_only",
            "scope": {},
        },
        expected=201,
    )
    policy_id = str(created["data"]["id"])
    print(f"已创建门禁策略：{policy_id}")
    return policy_id


async def _ensure_active_case(owner: AsyncClient, admin: AsyncClient) -> str:
    listing = await _get(owner, f"/api/v1/test-cases?project_id={PROJECT_ID}")
    active = [
        row
        for row in listing.get("data", {}).get("items") or []
        if row.get("lifecycle_status") == "ACTIVE"
    ]
    if active:
        case_id = str(active[0]["id"])
        print(f"ACTIVE 用例已存在：{case_id}")
        return case_id
    created = await _post(
        owner,
        "/api/v1/test-cases",
        {
            "project_id": PROJECT_ID,
            "case_type": "api",
            "execution_mode": "script",
            "title": "教程用例 GET openid-configuration",
            "drafts": [
                {
                    "steps": [
                        {
                            "action": "request",
                            "params": {
                                "method": "GET",
                                "path": "/.well-known/openid-configuration",
                            },
                        }
                    ],
                    "assertions": [{"type": "status_code", "expected": 200}],
                }
            ],
        },
        expected=201,
    )
    case_id = str(created["data"]["id"])
    submitted = await _post(
        owner,
        f"/api/v1/test-cases/{case_id}/submit-review",
        {"expected_version": created["data"]["version"]},
    )
    reviewed = await _post(
        admin,
        f"/api/v1/test-cases/{case_id}/review",
        {"expected_version": submitted["data"]["version"], "decision": "approve"},
    )
    status = reviewed["data"]["lifecycle_status"]
    if status != "ACTIVE":
        raise SystemExit(f"用例未进入 ACTIVE：{status}")
    print(f"已创建 ACTIVE 用例：{case_id}")
    return case_id


async def _ensure_tutorial_env(owner: AsyncClient, admin: AsyncClient) -> str:
    listing = await _get(owner, f"/api/v1/execution-environments?project_id={PROJECT_ID}")
    match = next(
        (
            row
            for row in listing.get("data", {}).get("items") or []
            if row.get("name") == ENV_NAME and row.get("status") == "ACTIVE"
        ),
        None,
    )
    if match:
        env_id = str(match["id"])
        print(f"执行环境已存在：{env_id} ({ENV_NAME})")
        return env_id
    registered = await _post(
        owner,
        "/api/v1/execution-environments",
        {
            "env_type": "platform_executor",
            "name": ENV_NAME,
            "scope_level": "project",
            "project_id": PROJECT_ID,
        },
    )
    status = registered["data"]["status"]
    if status != "PENDING_APPROVAL":
        raise SystemExit(f"环境注册未进入 PENDING_APPROVAL：{status}")
    approval_id = registered["data"]["approval_request_id"]
    detail = await _get(admin, f"/api/v1/approval-requests/{approval_id}")
    approved = await _post(
        admin,
        f"/api/v1/approval-requests/{approval_id}/decisions",
        {"decision": "approve", "expected_version": detail["data"]["version"]},
    )
    if approved["data"]["status"] != "EXECUTED":
        raise SystemExit(f"env_register 审批未 EXECUTED：{approved['data']['status']}")
    env = await _get(owner, f"/api/v1/execution-environments/{registered['data']['id']}")
    if env["data"]["status"] != "ACTIVE":
        raise SystemExit(f"环境未 ACTIVE：{env['data']['status']}")
    env_id = str(env["data"]["id"])
    print(f"已注册并四眼批准环境：{env_id} ({ENV_NAME})")
    return env_id


async def main() -> None:
    owner_cookie = await _login(USERNAMES["owner"])
    admin_cookie = await _login(USERNAMES["admin"])

    name = _cookie_name()
    async with (
        AsyncClient(base_url=BASE, cookies={name: owner_cookie}, timeout=30.0) as owner,
        AsyncClient(base_url=BASE, cookies={name: admin_cookie}, timeout=30.0) as admin,
    ):
        me = await _get(owner, "/api/v1/me")
        org = me.get("data", {}).get("organization", {})
        print(f"已登录 owner={USERNAMES['owner']} org={org.get('slug')}")
        policy_id = await _ensure_policy(owner)
        case_id = await _ensure_active_case(owner, admin)
        env_id = await _ensure_tutorial_env(owner, admin)
        print(f"§2 教程数据就绪：policy={policy_id} case={case_id} env={env_id}")


if __name__ == "__main__":
    asyncio.run(main())
