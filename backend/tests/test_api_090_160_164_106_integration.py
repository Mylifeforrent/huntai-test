import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import ProjectMember, User
from app.modules.integration_hub import repository as connector_repo
from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_admin_peer

TEST_WEBHOOK_SECRET = "test-github-webhook-secret"


def _github_signature(body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def _seed_connector(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    connector_type: str = "github",
    name: str = "GitHub Org",
    webhook_secret_ref: str | None = "env:GITHUB_WEBHOOK_SECRET",
    credential_ref: str = "",
) -> uuid.UUID:
    now = datetime.now(UTC)
    connector = await connector_repo.create_connector(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        connector_type=connector_type,
        name=name,
        webhook_secret_ref=webhook_secret_ref,
        credential_ref=credential_ref,
    )
    await db_session.commit()
    return connector.id


async def _seed_tester(
    db_session: AsyncSession,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    idp_subject: str = "tester-integration",
) -> uuid.UUID:
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    db_session.add(
        User(
            id=user_id,
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            idp_subject=idp_subject,
            display_name="Tester",
            email=f"{idp_subject}@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role="tester",
        )
    )
    await db_session.commit()
    return user_id


@pytest.mark.asyncio
async def test_api_160_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/connectors")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_160_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_tester(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await login_as(client, idp_subject="tester-integration")
    response = await client.get("/api/v1/connectors")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_160_161_owner_list_and_detail_no_secrets(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(
        db_session,
        org_id=org_id,
        user_id=user_id,
        credential_ref="env:GITHUB_WEBHOOK_SECRET",
    )
    await login_as(client)
    list_response = await client.get("/api/v1/connectors")
    assert list_response.status_code == 200
    list_text = list_response.text
    assert "credential_ref" not in list_text
    assert "webhook_secret_ref" not in list_text
    assert TEST_WEBHOOK_SECRET not in list_text
    items = list_response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["credential_present"] is True
    assert items[0]["webhook_secret_present"] is True

    detail_response = await client.get(f"/api/v1/connectors/{connector_id}")
    assert detail_response.status_code == 200
    detail_text = detail_response.text
    assert "credential_ref" not in detail_text
    assert "webhook_secret_ref" not in detail_text
    assert TEST_WEBHOOK_SECRET not in detail_text
    detail = detail_response.json()["data"]
    assert detail["id"] == str(connector_id)
    assert detail["version"] == 1


@pytest.mark.asyncio
async def test_api_090_missing_hmac_fails_no_test_runs(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"action": "opened"}).encode("utf-8")
    response = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-004"

    count_result = await db_session.execute(
        text("SELECT COUNT(*) FROM run_orchestration.test_runs")
    )
    assert count_result.scalar_one() == 0


@pytest.mark.asyncio
async def test_api_090_bad_hmac_fails(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"zen": "test"}).encode("utf-8")
    response = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Delivery": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-004"


@pytest.mark.asyncio
async def test_api_090_valid_hmac_after_failed_attempt_is_accepted(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"action": "synchronize"}).encode("utf-8")
    delivery_id = str(uuid.uuid4())
    failed = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert failed.status_code == 401

    accepted = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body),
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert accepted.status_code == 202
    data = accepted.json()["data"]
    assert data["accepted"] is True
    assert data["duplicate"] is False

    observation = await connector_repo.get_observation_by_key(
        db_session,
        organization_id=org_id,
        source="webhook",
        observation_key=f"{connector_id}:{delivery_id}",
    )
    assert observation is not None
    assert observation.signature_ok is True


@pytest.mark.asyncio
async def test_api_090_good_hmac_accepted(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"repository": {"full_name": "org/repo"}}).encode("utf-8")
    delivery_id = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body),
            "X-GitHub-Delivery": delivery_id,
            "X-GitHub-Event": "push",
        },
    )
    assert response.status_code == 202
    data = response.json()["data"]
    assert data["accepted"] is True
    assert data["duplicate"] is False
    assert data["observation_id"]

    count_result = await db_session.execute(
        text("SELECT COUNT(*) FROM run_orchestration.test_runs")
    )
    assert count_result.scalar_one() == 0


@pytest.mark.asyncio
async def test_api_090_replay_duplicate(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"hook_id": 1}).encode("utf-8")
    delivery_id = str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _github_signature(body),
        "X-GitHub-Delivery": delivery_id,
    }
    first = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers=headers,
    )
    assert first.status_code == 202
    first_id = first.json()["data"]["observation_id"]

    second = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers=headers,
    )
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["duplicate"] is True
    assert second_data["observation_id"] == first_id


@pytest.mark.asyncio
async def test_api_090_unknown_connector_not_found(client: AsyncClient) -> None:
    body = b"{}"
    response = await client.post(
        f"/api/v1/inbound-webhooks/{uuid.uuid4()}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body),
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_164_lists_delivery_without_payload_dump(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    body = json.dumps({"ref": "refs/heads/main"}).encode("utf-8")
    delivery_id = str(uuid.uuid4())
    webhook = await client.post(
        f"/api/v1/inbound-webhooks/{connector_id}",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _github_signature(body),
            "X-GitHub-Delivery": delivery_id,
        },
    )
    assert webhook.status_code == 202

    await login_as(client)
    response = await client.get(f"/api/v1/connectors/{connector_id}/webhook-deliveries")
    assert response.status_code == 200
    text = response.text
    assert "repository" not in text
    assert "refs/heads" not in text
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["signature_ok"] is True
    assert items[0]["observation_key"] == f"{connector_id}:{delivery_id}"
    assert items[0]["payload_ref"].startswith("sha256:")


@pytest.mark.asyncio
async def test_api_106_unknown_connector_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.post(
        f"/api/v1/connectors/{uuid.uuid4()}/credential-refs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"credential_ref": "env:GITHUB_WEBHOOK_SECRET", "expected_version": 1},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_106_invalid_ref_validation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    await login_as(client)
    response = await client.post(
        f"/api/v1/connectors/{connector_id}/credential-refs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"credential_ref": "ref-only"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_106_happy_bind_allowlisted_ref(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id, user_id=user_id)
    await login_as(client)
    bind = await client.post(
        f"/api/v1/connectors/{connector_id}/credential-refs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"credential_ref": "env:GITHUB_WEBHOOK_SECRET"},
    )
    assert bind.status_code == 200
    bind_data = bind.json()["data"]
    assert bind_data["has_credential"] is True
    assert bind_data["version"] == 2
    assert "credential_ref" not in bind.text

    detail = await client.get(f"/api/v1/connectors/{connector_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["credential_present"] is True
    assert "credential_ref" not in detail.text


@pytest.mark.asyncio
async def test_api_160_admin_peer_can_list(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_admin_peer(db_session, org_id=seeded_identity["org_id"], project_id=project_id)  # type: ignore[arg-type]
    await _seed_connector(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        user_id=seeded_identity["user_id"],  # type: ignore[arg-type]
    )
    await login_as(client, idp_subject="admin-peer-120")
    response = await client.get("/api/v1/connectors")
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 1
