"""Cross-module commands for integration_hub (no ORM export to consumers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub import query_port as integration_query
from app.modules.integration_hub import repository as repo
from app.modules.integration_hub.jira_write_stub import (
    derive_external_request_id,
    sync_jira_write_stub,
)
from app.modules.results_evidence import command_port as evidence_command
from app.modules.results_evidence import query_port as evidence_query
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

POLL_SOURCE = "poll"


async def record_poll_observation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    job_id: str,
    build_number: int,
    event_kind: str,
    payload_ref: str | None = None,
) -> None:
    connector = await integration_query.get_ci_connector(
        session,
        organization_id=organization_id,
    )
    if connector is None:
        return
    connector_id = connector["id"]
    assert isinstance(connector_id, uuid.UUID)
    observation_key = f"poll:{connector_id}:{job_id}:{build_number}:{event_kind}"
    existing = await repo.get_observation_by_key(
        session,
        organization_id=organization_id,
        source=POLL_SOURCE,
        observation_key=observation_key,
    )
    if existing is not None:
        return
    now = datetime.now(UTC)
    try:
        await repo.create_observation(
            session,
            organization_id=organization_id,
            connector_id=connector_id,
            source=POLL_SOURCE,
            observation_key=observation_key,
            payload_ref=payload_ref,
            signature_ok=True,
            observed_at=now,
            data_classification="Internal",
        )
    except IntegrityError:
        return


async def execute_jira_write_after_approval(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    approval_id: uuid.UUID,
    bound_hash: str,
    actor_user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    target_object_type: str,
    target_object_id: uuid.UUID,
    payload: dict[str, Any],
    request_hash: str,
) -> dict[str, Any]:
    connector = await integration_query.get_jira_write_connector(
        session,
        organization_id=organization_id,
    )
    if connector is None:
        return {"status": "failed", "reason": "connector_unavailable"}

    existing = await evidence_query.get_jira_issue_by_external_request_id(
        session,
        organization_id=organization_id,
        external_request_id=derive_external_request_id(
            organization_id=organization_id,
            approval_id=approval_id,
            bound_hash=bound_hash,
        ),
    )
    if existing is not None:
        return {
            "status": "ok",
            "external_request_id": existing.get("external_request_id") or "",
            "issue_key": existing["key"],
            "duplicate": True,
        }

    description = str(payload.get("description") or payload.get("summary") or "").strip()
    repro_steps = str(payload.get("repro_steps") or "").strip()
    jira_project = str(payload.get("jira_project") or "").strip()
    raw_evidence = payload.get("evidence_ids")
    parsed_evidence_ids: list[uuid.UUID] = []
    if isinstance(raw_evidence, list):
        for item in raw_evidence:
            try:
                parsed_evidence_ids.append(uuid.UUID(str(item)))
            except (TypeError, ValueError):  # fmt: skip
                return {"status": "failed", "reason": "invalid_evidence"}
    evidence_ids = [str(item) for item in parsed_evidence_ids]

    if parsed_evidence_ids:
        classifications = await evidence_query.get_evidence_classifications(
            session,
            organization_id=organization_id,
            evidence_ids=parsed_evidence_ids,
        )
        if any(item == "Restricted" for item in classifications.values()):
            return {"status": "failed", "reason": "restricted_evidence"}

    stub_result = await sync_jira_write_stub(
        session,
        organization_id=organization_id,
        approval_id=approval_id,
        bound_hash=bound_hash,
        jira_project=jira_project,
        description=description,
        repro_steps=repro_steps,
        evidence_ids=evidence_ids,
        request_hash=request_hash,
    )
    if stub_result["status"] != "ok" or stub_result.get("issue_key") is None:
        return {"status": "failed", "reason": "stub_failed"}

    now = datetime.now(UTC)
    issue_key = str(stub_result["issue_key"])
    external_request_id = str(stub_result["external_request_id"])
    await evidence_command.append_jira_issue_evidence(
        session,
        organization_id=organization_id,
        created_at=now,
        created_by=actor_user_id,
        subject_type=target_object_type,
        subject_id=target_object_id,
        issue_key=issue_key,
        external_request_id=external_request_id,
        evidence_ids=parsed_evidence_ids,
        approval_id=approval_id,
        bound_hash=bound_hash,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="jira_write",
            resource_type=target_object_type,
            resource_id=target_object_id,
            project_id=project_id,
            result="ok",
            request_hash=request_hash,
            external_request_id=external_request_id,
            approval_id=approval_id,
            approval_bound_hash=bound_hash,
            evidence_refs=parsed_evidence_ids or None,
        ),
    )
    return {
        "status": "ok",
        "external_request_id": external_request_id,
        "issue_key": issue_key,
        "duplicate": False,
    }


__all__ = ["execute_jira_write_after_approval", "record_poll_observation"]
