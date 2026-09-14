import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import Organization
from app.modules.integration_hub import repository as connector_repo
from tests.helpers import login_as
from tests.test_api_090_160_164_106_integration import _seed_connector, _seed_tester


def _channels_path(connector_id: uuid.UUID) -> str:
    return f"/api/v1/connectors/{connector_id}/outbound-channels"


def _put_body(
    *,
    expected_version: int = 1,
    channels: list[dict[str, object]],
) -> dict[str, object]:
    return {"expected_version": expected_version, "channels": channels}


@pytest.mark.asyncio
async def test_api_165_166_unauthenticated(client: AsyncClient) -> None:
    connector_id = uuid.uuid4()
    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 401
    assert get_response.json()["error"]["code"] == "HT-AUTH-001"

    put_response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(channels=[]),
    )
    assert put_response.status_code == 401
    assert put_response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_165_166_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    org_id = seeded_identity["org_id"]
    assert isinstance(org_id, uuid.UUID)
    connector_id = await _seed_connector(db_session, org_id=org_id)
    await _seed_tester(db_session, org_id=org_id, project_id=project_id)
    await login_as(client, idp_subject="tester-integration")

    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 403
    assert get_response.json()["error"]["code"] == "HT-IAM-001"

    put_response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(channels=[]),
    )
    assert put_response.status_code == 403
    assert put_response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_165_166_unknown_connector_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    mock_oidc_token_exchange: object,
) -> None:
    _ = seeded_identity
    _ = mock_oidc_token_exchange
    await login_as(client)
    connector_id = uuid.uuid4()

    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "HT-RES-001"

    put_response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(channels=[]),
    )
    assert put_response.status_code == 404
    assert put_response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_165_166_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other Org",
            slug="other-org",
            capability_controls={},
            siem_export={},
            is_active=True,
        )
    )
    await db_session.flush()
    connector_id = await _seed_connector(
        db_session,
        org_id=other_org,
        user_id=other_user,
        name="Other Connector",
    )
    await login_as(client)

    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 404
    assert get_response.json()["error"]["code"] == "HT-RES-001"

    put_response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(channels=[]),
    )
    assert put_response.status_code == 404
    assert put_response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_165_166_happy_put_get_no_secrets(
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

    put_response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {
                    "kind": "wecom",
                    "is_primary": True,
                    "endpoint_ref": "env:GITHUB_WEBHOOK_SECRET",
                }
            ]
        ),
    )
    assert put_response.status_code == 200
    put_text = put_response.text
    assert "endpoint_ref" not in put_text
    assert "GITHUB_WEBHOOK_SECRET" not in put_text
    assert "http" not in put_text.lower()
    put_data = put_response.json()["data"]
    assert put_data["connector_version"] == 2
    assert len(put_data["items"]) == 1
    put_item = put_data["items"][0]
    assert put_item["channel_type"] == "wecom"
    assert put_item["is_primary"] is True
    assert put_item["endpoint_present"] is True
    assert put_item["enabled"] is True

    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 200
    get_text = get_response.text
    assert "endpoint_ref" not in get_text
    assert "GITHUB_WEBHOOK_SECRET" not in get_text
    assert "http" not in get_text.lower()
    get_data = get_response.json()["data"]
    assert get_data["connector_version"] == 2
    assert get_data["items"] == put_data["items"]
    assert get_response.json()["page"]["next_cursor"] is None


@pytest.mark.asyncio
async def test_api_166_validation_errors(
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

    two_primaries = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {"kind": "wecom", "is_primary": True, "endpoint_ref": "env:FOO"},
                {"kind": "dingtalk", "is_primary": True, "endpoint_ref": "env:BAR"},
            ]
        ),
    )
    assert two_primaries.status_code == 400
    assert two_primaries.json()["error"]["code"] == "HT-VAL-001"

    zero_primary = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {"kind": "wecom", "is_primary": False, "endpoint_ref": "env:FOO"},
            ]
        ),
    )
    assert zero_primary.status_code == 400
    assert zero_primary.json()["error"]["code"] == "HT-VAL-001"

    inline_https = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {
                    "kind": "wecom",
                    "is_primary": True,
                    "endpoint_ref": "https://example.com/hook",
                }
            ]
        ),
    )
    assert inline_https.status_code == 400
    assert inline_https.json()["error"]["code"] == "HT-VAL-001"

    missing_env_prefix = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {
                    "kind": "wecom",
                    "is_primary": True,
                    "endpoint_ref": "GITHUB_WEBHOOK_SECRET",
                }
            ]
        ),
    )
    assert missing_env_prefix.status_code == 400
    assert missing_env_prefix.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_166_version_conflict(
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

    response = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(expected_version=99, channels=[]),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_api_166_idempotency_replay(
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

    body = _put_body(
        channels=[
            {
                "kind": "wecom",
                "is_primary": True,
                "endpoint_ref": "env:GITHUB_WEBHOOK_SECRET",
            }
        ]
    )
    idem_key = str(uuid.uuid4())
    first = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert first.status_code == 200
    first_version = first.json()["data"]["connector_version"]

    second = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert second.status_code == 200
    assert second.json()["data"]["connector_version"] == first_version

    connector = await connector_repo.get_connector(
        db_session,
        organization_id=org_id,
        connector_id=connector_id,
    )
    assert connector is not None
    assert connector.aggregate_version == first_version


@pytest.mark.asyncio
async def test_api_166_idempotency_hash_mismatch(
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

    idem_key = str(uuid.uuid4())
    first = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": idem_key},
        json=_put_body(
            channels=[
                {
                    "kind": "wecom",
                    "is_primary": True,
                    "endpoint_ref": "env:GITHUB_WEBHOOK_SECRET",
                }
            ]
        ),
    )
    assert first.status_code == 200

    conflict = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": idem_key},
        json=_put_body(
            expected_version=first.json()["data"]["connector_version"],
            channels=[],
        ),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-IDEM-001"


@pytest.mark.asyncio
async def test_api_165_166_clear_channels(
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

    seed = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(
            channels=[
                {
                    "kind": "wecom",
                    "is_primary": True,
                    "endpoint_ref": "env:GITHUB_WEBHOOK_SECRET",
                }
            ]
        ),
    )
    assert seed.status_code == 200
    version = seed.json()["data"]["connector_version"]

    clear = await client.put(
        _channels_path(connector_id),
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_put_body(expected_version=version, channels=[]),
    )
    assert clear.status_code == 200
    assert clear.json()["data"]["items"] == []

    get_response = await client.get(_channels_path(connector_id))
    assert get_response.status_code == 200
    assert get_response.json()["data"]["items"] == []
