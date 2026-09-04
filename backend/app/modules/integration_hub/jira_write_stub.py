"""Jira defect write stub (no real HTTP)."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
    issue_key = derive_issue_key(external_request_id)
    stub_payload = {
        "project": jira_project,
        "summary": description[:255],
        "description": description,
        "repro_steps": repro_steps,
        "evidence_ids": list(evidence_ids),
    }

    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        try:
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
