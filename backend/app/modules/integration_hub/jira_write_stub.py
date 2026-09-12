"""Jira defect write stub; loopback mock uses HTTP when configured."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub.query_port import get_loopback_outbound_target
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

MAX_SYNC_ATTEMPTS = 3


class JiraWriteSyncError(Exception):
    """Raised when stub write fails (for bounded retry testing)."""


def derive_external_request_id(
    *,
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    bound_hash: str,
) -> str:
    canonical = f"{organization_id}:{approval_id}:{bound_hash}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def derive_issue_key(external_request_id: str) -> str:
    short = external_request_id[:8].upper()
    return f"HT-{short}"


async def _apply_write(result: dict[str, Any]) -> dict[str, Any]:
    """Phase hook so tests can inject JiraWriteSyncError (no real HTTP)."""
    return result


async def _post_jira_issue_loopback(
    *,
    base_url: str,
    external_request_id: str,
    jira_project: str,
    description: str,
) -> str:
    url = f"{base_url.rstrip('/')}/rest/api/2/issue"
    body = {
        "fields": {
            "project": {"key": jira_project or "HT"},
            "summary": description[:255],
            "description": description,
        }
    }
    headers = {"X-External-Request-Id": external_request_id}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise JiraWriteSyncError(str(exc)) from exc
    if response.status_code >= 500:
        raise JiraWriteSyncError(f"HTTP {response.status_code}")
    if response.status_code not in (200, 201):
        raise JiraWriteSyncError(f"HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise JiraWriteSyncError("invalid response body")
    issue_key = payload.get("key")
    if not isinstance(issue_key, str) or not issue_key.strip():
        raise JiraWriteSyncError("missing issue key")
    return issue_key.strip()


async def sync_jira_write_stub(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    bound_hash: str,
    jira_project: str,
    description: str,
    repro_steps: str,
    evidence_ids: list[str],
    request_hash: str,
) -> dict[str, Any]:
    external_request_id = derive_external_request_id(
        organization_id=organization_id,
        approval_id=approval_id,
        bound_hash=bound_hash,
    )
    loopback_target = await get_loopback_outbound_target(
        session,
        organization_id=organization_id,
        connector_type="jira",
    )
    stub_payload = {
        "project": jira_project,
        "summary": description[:255],
        "description": description,
        "repro_steps": repro_steps,
        "evidence_ids": list(evidence_ids),
    }

    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        try:
            if loopback_target is not None:
                issue_key = await _post_jira_issue_loopback(
                    base_url=str(loopback_target["base_url"]),
                    external_request_id=external_request_id,
                    jira_project=jira_project,
                    description=description,
                )
                return {
                    "status": "ok",
                    "external_request_id": external_request_id,
                    "issue_key": issue_key,
                    "stub_payload": stub_payload,
                    "attempts": attempt,
                }
            issue_key = derive_issue_key(external_request_id)
            return await _apply_write(
                {
                    "status": "ok",
                    "external_request_id": external_request_id,
                    "issue_key": issue_key,
                    "stub_payload": stub_payload,
                    "attempts": attempt,
                }
            )
        except JiraWriteSyncError:
            if attempt >= MAX_SYNC_ATTEMPTS:
                break
            continue

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=None,
            action="jira_write.sync_failed",
            resource_type="approval_request",
            resource_id=approval_id,
            result="failed",
            request_hash=request_hash,
            external_request_id=external_request_id,
        ),
    )
    return {
        "status": "failed",
        "external_request_id": external_request_id,
        "issue_key": None,
        "stub_payload": stub_payload,
        "attempts": MAX_SYNC_ATTEMPTS,
    }
