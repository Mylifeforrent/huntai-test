"""Idempotent local integration connector seed for mock server. Not a product bootstrap path."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import Project
from app.modules.integration_hub.models import Connector

JIRA_PROJECT_KEY = "HT"
MOCK_HOST = "127.0.0.1:8091"

JIRA_CONNECTOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000010")
GITHUB_CONNECTOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000011")
CI_CONNECTOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000012")
RELEASE_CONNECTOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000013")


@dataclass(frozen=True, slots=True)
class ConnectorSeedSpec:
    id: uuid.UUID
    connector_type: str
    name: str
    credential_ref: str
    webhook_secret_ref: str | None
    base_url: str


CONNECTOR_SPECS: tuple[ConnectorSeedSpec, ...] = (
    ConnectorSeedSpec(
        id=JIRA_CONNECTOR_ID,
        connector_type="jira",
        name="Local mock Jira",
        credential_ref="env:JENKINS_API_TOKEN",
        webhook_secret_ref=None,
        base_url=f"http://{MOCK_HOST}/jira",
    ),
    ConnectorSeedSpec(
        id=GITHUB_CONNECTOR_ID,
        connector_type="github",
        name="Local mock GitHub",
        credential_ref="env:GITHUB_WEBHOOK_SECRET",
        webhook_secret_ref="env:GITHUB_WEBHOOK_SECRET",
        base_url=f"http://{MOCK_HOST}/github",
    ),
    ConnectorSeedSpec(
        id=CI_CONNECTOR_ID,
        connector_type="ci",
        name="Local mock Jenkins",
        credential_ref="env:JENKINS_API_TOKEN",
        webhook_secret_ref="env:JENKINS_WEBHOOK_SECRET",
        base_url=f"http://{MOCK_HOST}/jenkins",
    ),
    ConnectorSeedSpec(
        id=RELEASE_CONNECTOR_ID,
        connector_type="release",
        name="Local mock Release",
        credential_ref="env:JENKINS_API_TOKEN",
        webhook_secret_ref="env:GITHUB_WEBHOOK_SECRET",
        base_url=f"http://{MOCK_HOST}/release",
    ),
)


def _action_contract(spec: ConnectorSeedSpec) -> dict[str, Any]:
    contract: dict[str, Any] = {"base_url": spec.base_url, "sideEffectLevel": "L2"}
    if spec.connector_type == "github":
        contract["owner"] = "local-dev"
        contract["repo"] = "demo"
    return contract


async def _get_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    spec: ConnectorSeedSpec,
) -> Connector | None:
    by_id_result = await session.execute(
        select(Connector).where(
            Connector.organization_id == organization_id,
            Connector.id == spec.id,
        )
    )
    by_id = by_id_result.scalar_one_or_none()
    if by_id is not None:
        return by_id
    by_name_result = await session.execute(
        select(Connector).where(
            Connector.organization_id == organization_id,
            Connector.type == spec.connector_type,
            Connector.name == spec.name,
        )
    )
    return by_name_result.scalar_one_or_none()


def _apply_connector_fields(
    connector: Connector,
    *,
    spec: ConnectorSeedSpec,
    now: datetime,
) -> None:
    contract = _action_contract(spec)
    connector.credential_ref = spec.credential_ref
    connector.webhook_secret_ref = spec.webhook_secret_ref
    connector.action_contract = contract
    connector.outbound_write_enabled = True
    connector.updated_at = now


async def _upsert_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    spec: ConnectorSeedSpec,
    now: datetime,
) -> None:
    connector = await _get_connector(session, organization_id=organization_id, spec=spec)
    if connector is None:
        session.add(
            Connector(
                id=spec.id,
                organization_id=organization_id,
                created_at=now,
                updated_at=now,
                created_by=created_by,
                aggregate_version=1,
                type=spec.connector_type,
                name=spec.name,
                auth_method="hmac",
                credential_ref=spec.credential_ref,
                action_contract=_action_contract(spec),
                outbound_write_enabled=True,
                webhook_secret_ref=spec.webhook_secret_ref,
                standing_auth_metadata=None,
                config_version=1,
                health_status=None,
            )
        )
        await session.flush()
        return

    _apply_connector_fields(connector, spec=spec, now=now)
    await session.flush()


async def _ensure_jira_project_key(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    now: datetime,
) -> None:
    project = await session.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        return
    if project.jira_project_key != JIRA_PROJECT_KEY:
        project.jira_project_key = JIRA_PROJECT_KEY
        project.updated_at = now


async def seed_local_integrations(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    now: datetime,
) -> list[str]:
    """Seed local mock connectors and project Jira key. Returns connector types seeded."""
    await _ensure_jira_project_key(session, project_id=project_id, now=now)
    for spec in CONNECTOR_SPECS:
        await _upsert_connector(
            session,
            organization_id=organization_id,
            created_by=created_by,
            spec=spec,
            now=now,
        )
    types = [spec.connector_type for spec in CONNECTOR_SPECS]
    print(
        "seeded connectors: "
        + ", ".join(types)
        + f" (ids {JIRA_CONNECTOR_ID} … {RELEASE_CONNECTOR_ID})"
    )
    return types
