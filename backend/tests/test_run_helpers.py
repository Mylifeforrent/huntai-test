"""Shared helpers for TestRun API tests."""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import login_as
from tests.test_api_100_106_env_registry import _register_environment
from tests.test_api_120_action_previews import _seed_admin_peer


async def activate_platform_executor_env(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    name: str = "Platform Executor",
) -> dict[str, object]:
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
    )
    await login_as(client)
    created = await _register_environment(
        client,
        project_id,
        name=name,
        scope_level="project",
    )
    from app.modules.execution_registry import repository as env_repo

    bound = await env_repo.get_environment(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        environment_id=uuid.UUID(str(created["id"])),
    )
    assert bound is not None
    bound.env_type = "platform_executor"
    await db_session.commit()
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
    assert env.json()["data"]["env_type"] == "platform_executor"
    return env.json()["data"]


async def create_active_script_case(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    title: str = "HTTP case",
    steps: list[dict[str, Any]] | None = None,
    assertions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "api",
            "execution_mode": "script",
            "title": title,
            "drafts": [
                {
                    "steps": steps
                    or [{"action": "request", "params": {"method": "GET", "path": "/pets"}}],
                    "assertions": assertions or [{"type": "status_code", "expected": 200}],
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
    assert approve.json()["data"]["lifecycle_status"] == "ACTIVE"
    return approve.json()["data"]


async def activate_external_ci_env(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    job_id: str = "smoke-suite",
    name: str = "External CI",
    params_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    proj_id = seeded_identity["project_id"]
    assert isinstance(proj_id, uuid.UUID)
    await _seed_admin_peer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=proj_id,
    )
    schema = params_schema or {
        "type": "object",
        "required": ["branch"],
        "properties": {"branch": {"type": "string"}},
    }
    await login_as(client)
    created = await _register_environment(
        client,
        proj_id,
        name=name,
        scope_level="project",
        job_contracts=[
            {
                "job_id": job_id,
                "supports_cancel": True,
                "contract_version": 1,
                "report_adapter": "junit",
                "schema": schema,
                "artifact_manifest": {"junit_path": "junit.xml"},
            }
        ],
    )
    from app.modules.execution_registry import repository as env_repo

    bound = await env_repo.get_environment(
        db_session,
        organization_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        environment_id=uuid.UUID(str(created["id"])),
    )
    assert bound is not None
    bound.credential_ref = "env:JENKINS_API_TOKEN"
    await db_session.commit()
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
    assert env.json()["data"]["env_type"] == "external_ci"
    return env.json()["data"]


async def create_active_referenced_case(
    client: AsyncClient,
    *,
    project_id: uuid.UUID,
    env_id: str,
    job_id: str = "smoke-suite",
    title: str = "Referenced CI case",
    artifact_path: str = "junit.xml",
) -> dict[str, Any]:
    await login_as(client)
    create = await client.post(
        "/api/v1/test-cases",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "project_id": str(project_id),
            "case_type": "referenced",
            "execution_mode": "script",
            "title": title,
            "job_binding": {
                "env_id": env_id,
                "job_id": job_id,
                "collect_config": {"artifact_path": artifact_path},
            },
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
    assert approve.json()["data"]["lifecycle_status"] == "ACTIVE"
    return approve.json()["data"]
