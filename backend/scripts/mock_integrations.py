"""Local-only integration mocks (Jira, GitHub, Jenkins, Release). Not a product API."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8091
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
FORBIDDEN_BODY_KEYS = frozenset(
    {
        "secret",
        "webhook_secret",
        "token",
        "password",
        "api_key",
        "api_token",
        "credential",
        "credential_ref",
        "authorization",
    }
)

JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="mock" tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="mock.Pass" name="test_passing" time="0.01"/>
  <testcase classname="mock.Fail" name="test_failing" time="0.01">
    <failure message="expected failure">AssertionError: demo failure</failure>
  </testcase>
</testsuite>
"""

CONFLUENCE_OPENAPI: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Local Demo Orders API", "version": "1.0.0"},
    "paths": {
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {"200": {"description": "OK"}},
            }
        }
    },
}


def _normalize_host(host: str) -> str:
    return host.strip("[]").lower()


def is_loopback_host(host: str) -> bool:
    """Return True when ``host`` is a loopback interface."""
    return _normalize_host(host) in LOOPBACK_HOSTS


def require_loopback_host(host: str) -> None:
    """Exit when ``host`` is not loopback."""
    if not is_loopback_host(host):
        raise SystemExit("mock integrations only listens on loopback hosts")


def _client_is_loopback(request: Request) -> bool:
    client = request.client
    if client is None:
        return True
    return is_loopback_host(client.host)


def _mock_base_url(host: str, port: int) -> str:
    display_host = host if host != "::1" else "[::1]"
    return f"http://{display_host}:{port}"


def _short_id(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


@dataclass
class CheckRun:
    owner: str
    repo: str
    status: str = "queued"
    conclusion: str | None = None
    html_url: str = ""


@dataclass
class JenkinsBuild:
    job_id: str
    number: int
    building: bool = False
    result: str = "FAILURE"
    log_text: str = field(
        default_factory=lambda: (
            "Started by HuntAI local mock\n"
            "Running smoke checks...\n"
            "FAIL test_failing\n"
            "Finished: FAILURE\n"
        )
    )


@dataclass
class MockState:
    issue_counter: int = 0
    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    issue_idempotency: dict[str, str] = field(default_factory=dict)
    check_run_counter: int = 0
    check_runs: dict[int, CheckRun] = field(default_factory=dict)
    jenkins_jobs: set[str] = field(default_factory=lambda: {"local-demo", "smoke-suite"})
    queue_counter: int = 0
    queue_items: dict[int, int] = field(default_factory=dict)
    job_build_counter: dict[str, int] = field(default_factory=dict)
    builds: dict[tuple[str, int], JenkinsBuild] = field(default_factory=dict)
    release_items: dict[str, dict[str, str]] = field(default_factory=dict)


_state = MockState()


def reset_state() -> None:
    """Clear in-memory stores (for tests)."""
    global _state
    _state = MockState()


def _next_issue_id() -> int:
    _state.issue_counter += 1
    return _state.issue_counter


def _issue_key(issue_id: int) -> str:
    return f"HT-{issue_id}"


def _accept_auth(request: Request) -> None:
    _ = request.headers.get("authorization")


def _jenkins_auth_ok(request: Request) -> bool:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return False
    try:
        raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except UnicodeDecodeError, ValueError:
        return False
    _username, _sep, password = raw.partition(":")
    return bool(password)


def _reject_secrets_in_body(payload: dict[str, Any]) -> None:
    for key in payload:
        normalized = key.lower().replace("-", "_")
        if normalized in FORBIDDEN_BODY_KEYS or "secret" in normalized or "password" in normalized:
            raise HTTPException(status_code=400, detail="secrets must not appear in request body")


def _sign_webhook(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


class EmitWebhookBody(BaseModel):
    huntai_base: str
    connector_id: str
    event: str
    delivery_id: str
    body: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="HuntAI local integration mocks", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jira/rest/api/2/issue", status_code=201)
async def jira_create_issue(request: Request) -> JSONResponse:
    _accept_auth(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid body")
    base = _mock_base_url(DEFAULT_HOST, DEFAULT_PORT)
    external_id = request.headers.get("x-external-request-id")
    if external_id:
        existing_key = _state.issue_idempotency.get(external_id)
        if existing_key is not None:
            issue = _state.issues[existing_key]
            return JSONResponse(
                {
                    "id": issue["id"],
                    "key": existing_key,
                    "self": f"{base}/jira/rest/api/2/issue/{issue['id']}",
                },
                status_code=201,
            )
    issue_id = _next_issue_id()
    key = _issue_key(issue_id)
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    record = {
        "id": str(issue_id),
        "key": key,
        "fields": fields,
    }
    _state.issues[key] = record
    if external_id:
        _state.issue_idempotency[external_id] = key
    return JSONResponse(
        {
            "id": str(issue_id),
            "key": key,
            "self": f"{base}/jira/rest/api/2/issue/{issue_id}",
        },
        status_code=201,
    )


@app.get("/jira/rest/api/2/issue/{key}")
def jira_get_issue(key: str) -> dict[str, Any]:
    issue = _state.issues.get(key)
    if issue is None:
        raise HTTPException(status_code=404, detail="issue not found")
    return issue


@app.get("/jira/rest/api/2/project/HT/versions")
def jira_project_versions() -> list[dict[str, Any]]:
    return [{"id": "1000", "name": "1.0.0", "released": False}]


@app.post("/github/repos/{owner}/{repo}/check-runs", status_code=201)
async def github_create_check_run(owner: str, repo: str) -> dict[str, Any]:
    _state.check_run_counter += 1
    check_id = _state.check_run_counter
    html_url = f"http://127.0.0.1:8091/github/repos/{owner}/{repo}/check-runs/{check_id}"
    _state.check_runs[check_id] = CheckRun(
        owner=owner,
        repo=repo,
        status="queued",
        conclusion=None,
        html_url=html_url,
    )
    return {
        "id": check_id,
        "status": "queued",
        "conclusion": None,
        "html_url": html_url,
    }


@app.patch("/github/repos/{owner}/{repo}/check-runs/{check_id}")
async def github_update_check_run(
    owner: str,
    repo: str,
    check_id: int,
    request: Request,
) -> dict[str, Any]:
    record = _state.check_runs.get(check_id)
    if record is None or record.owner != owner or record.repo != repo:
        raise HTTPException(status_code=404, detail="check run not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid body")
    status = payload.get("status")
    if isinstance(status, str):
        record.status = status
    conclusion = payload.get("conclusion")
    if conclusion is not None:
        record.conclusion = str(conclusion) if conclusion else None
    return {
        "id": check_id,
        "status": record.status,
        "conclusion": record.conclusion,
        "html_url": record.html_url,
    }


@app.get("/jenkins/job/{job_id}/api/json")
def jenkins_job_api(job_id: str, request: Request) -> dict[str, Any]:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    if job_id not in _state.jenkins_jobs:
        raise HTTPException(status_code=404, detail="job not found")
    return {"buildable": True}


def _trigger_jenkins_build(job_id: str) -> tuple[int, int]:
    if job_id not in _state.jenkins_jobs:
        raise HTTPException(status_code=404, detail="job not found")
    _state.queue_counter += 1
    queue_id = _state.queue_counter
    build_number = _state.job_build_counter.get(job_id, 0) + 1
    _state.job_build_counter[job_id] = build_number
    _state.queue_items[queue_id] = build_number
    _state.builds[(job_id, build_number)] = JenkinsBuild(job_id=job_id, number=build_number)
    return queue_id, build_number


@app.post("/jenkins/job/{job_id}/build", status_code=201)
def jenkins_build(job_id: str, request: Request) -> Response:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    queue_id, _build_number = _trigger_jenkins_build(job_id)
    location = f"http://127.0.0.1:8091/jenkins/queue/item/{queue_id}/"
    return Response(status_code=201, headers={"Location": location})


@app.post("/jenkins/job/{job_id}/buildWithParameters", status_code=201)
def jenkins_build_with_parameters(job_id: str, request: Request) -> Response:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    queue_id, _build_number = _trigger_jenkins_build(job_id)
    location = f"http://127.0.0.1:8091/jenkins/queue/item/{queue_id}/"
    return Response(status_code=201, headers={"Location": location})


@app.get("/jenkins/queue/item/{queue_id}/api/json")
def jenkins_queue_item(queue_id: int, request: Request) -> dict[str, Any]:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    build_number = _state.queue_items.get(queue_id)
    if build_number is None:
        raise HTTPException(status_code=404, detail="queue item not found")
    return {"executable": {"number": build_number}}


def _jenkins_build_payload(job_id: str, build_number: int) -> dict[str, Any]:
    build = _state.builds.get((job_id, build_number))
    if build is None:
        raise HTTPException(status_code=404, detail="build not found")
    return {
        "number": build.number,
        "building": build.building,
        "result": build.result,
    }


@app.get("/jenkins/job/{job_id}/lastBuild/api/json")
def jenkins_last_build(job_id: str, request: Request) -> dict[str, Any]:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    build_number = _state.job_build_counter.get(job_id)
    if build_number is None:
        raise HTTPException(status_code=404, detail="no builds")
    return _jenkins_build_payload(job_id, build_number)


@app.get("/jenkins/job/{job_id}/{build_number}/api/json")
def jenkins_build_api(job_id: str, build_number: int, request: Request) -> dict[str, Any]:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    return _jenkins_build_payload(job_id, build_number)


@app.get("/jenkins/job/{job_id}/{build_number}/artifact/junit.xml")
def jenkins_junit_artifact(job_id: str, build_number: int, request: Request) -> Response:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    if (job_id, build_number) not in _state.builds:
        raise HTTPException(status_code=404, detail="build not found")
    return Response(content=JUNIT_XML, media_type="application/xml")


@app.get("/jenkins/job/{job_id}/{build_number}/logText/progressiveText")
def jenkins_progressive_log(
    job_id: str,
    build_number: int,
    request: Request,
    start: int = 0,
) -> PlainTextResponse:
    if not _jenkins_auth_ok(request):
        raise HTTPException(status_code=401, detail="authentication required")
    build = _state.builds.get((job_id, build_number))
    if build is None:
        raise HTTPException(status_code=404, detail="build not found")
    offset = max(start, 0)
    text = build.log_text[offset:]
    response = PlainTextResponse(content=text)
    response.headers["X-Text-Size"] = str(len(build.log_text))
    return response


@app.post("/release/items", status_code=201)
async def release_create_item(request: Request) -> JSONResponse:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid body")
    prepare_key = payload.get("prepare_key")
    if not isinstance(prepare_key, str) or not prepare_key:
        raise HTTPException(status_code=400, detail="prepare_key required")
    existing = _state.release_items.get(prepare_key)
    if existing is not None:
        return JSONResponse(existing, status_code=201)
    external_item_id = f"RI-{_short_id(prepare_key)}"
    record = {
        "external_system": "release_mock",
        "external_item_id": external_item_id,
    }
    _state.release_items[prepare_key] = record
    return JSONResponse(record, status_code=201)


@app.get("/confluence/")
def confluence_index() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Confluence demo</title></head>
<body>
  <h1>Confluence local demo</h1>
  <p>M4 RAG is out of scope for HuntAI Test. This page is demo-only and is
     <strong>NOT a connector</strong>; do not register <code>confluence</code>
     as a <code>Connector.type</code>.</p>
  <p>For A1 paste workflows, use the bundled OpenAPI document:
     <a href="/confluence/openapi.json">openapi.json</a>.</p>
</body>
</html>"""
    )


@app.get("/confluence/openapi.json")
def confluence_openapi() -> dict[str, Any]:
    return CONFLUENCE_OPENAPI


@app.post("/dev/emit-webhook")
async def dev_emit_webhook(request: Request) -> dict[str, Any]:
    if not _client_is_loopback(request):
        raise HTTPException(status_code=403, detail="loopback clients only")
    raw = await request.json()
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="invalid body")
    _reject_secrets_in_body(raw)
    if isinstance(raw.get("body"), dict):
        _reject_secrets_in_body(raw["body"])
    payload = EmitWebhookBody.model_validate(raw)
    settings = get_settings()
    secret = settings.github_webhook_secret
    if not secret:
        raise HTTPException(status_code=500, detail="webhook secret not configured")
    outbound_body = json.dumps(payload.body, separators=(",", ":"), sort_keys=True).encode()
    signature = _sign_webhook(outbound_body, secret)
    target = urljoin(
        payload.huntai_base.rstrip("/") + "/",
        f"api/v1/inbound-webhooks/{payload.connector_id}",
    )
    headers = {
        "content-type": "application/json",
        "x-hub-signature-256": signature,
        "x-github-delivery": payload.delivery_id,
        "x-github-event": payload.event,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(target, content=outbound_body, headers=headers)
    return {
        "delivered": True,
        "status_code": response.status_code,
        "target": target,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="HuntAI local integration mocks")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    require_loopback_host(args.host)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
