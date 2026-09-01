"""API-196/197/198 model routes and API-184/185 invocation logs."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.ai_governance.models import AIInvocationLog, ModelRoute
from app.modules.results_evidence.audit_models import AuditEvent
from tests.ai_governance_helpers import seed_model_routes, seed_tester
from tests.helpers import login_as


@pytest.mark.asyncio
async def test_api_196_owner_lists_routes_without_credential_ref(
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
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await login_as(client)

    response = await client.get("/api/v1/model-routes")
    assert response.status_code == 200
    body = response.json()
    items = body["data"]["items"]
    assert len(items) >= 2
    for item in items:
        assert "credential_ref" not in item
        assert "credential_present" in item
        assert "version" in item


@pytest.mark.asyncio
async def test_api_196_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await seed_tester(db_session, org_id=org_id, project_id=project_id)
    await login_as(client, idp_subject="tester-model-routes")

    response = await client.get("/api/v1/model-routes")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_197_put_updates_max_cost_and_idempotency(
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
    routes = await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    internal = next(item for item in routes if item["data_classification"] == "Internal")
    route_id = internal["id"]
    version = internal["version"]
    assert isinstance(route_id, uuid.UUID)
    assert isinstance(version, int)

    await login_as(client)
    body = {
        "expected_version": version,
        "task_type": "general",
        "data_classification": "Internal",
        "provider_allowlist": ["openai"],
        "max_cost": 25.5,
        "require_prompt_version": True,
        "require_structured_output": False,
    }
    idem_key = str(uuid.uuid4())
    put_resp = await client.put(
        f"/api/v1/model-routes/{route_id}",
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()["data"]
    assert updated["max_cost"] == 25.5
    assert updated["version"] == version + 1
    assert "credential_ref" not in updated

    replay = await client.put(
        f"/api/v1/model-routes/{route_id}",
        headers={"Idempotency-Key": idem_key},
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["max_cost"] == 25.5

    get_resp = await client.get("/api/v1/model-routes")
    match = next(item for item in get_resp.json()["data"]["items"] if item["id"] == str(route_id))
    assert match["max_cost"] == 25.5
    assert match["version"] == version + 1


@pytest.mark.asyncio
async def test_api_197_restricted_cloud_allowlist_policy_deny(
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
    routes = await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    restricted = next(item for item in routes if item["data_classification"] == "Restricted")
    route_id = restricted["id"]
    version = restricted["version"]
    assert isinstance(route_id, uuid.UUID)
    assert isinstance(version, int)

    await login_as(client)
    response = await client.put(
        f"/api/v1/model-routes/{route_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "task_type": "general",
            "data_classification": "Restricted",
            "provider_allowlist": ["openai"],
            "max_cost": 10,
            "require_prompt_version": True,
            "require_structured_output": False,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-POL-001"


@pytest.mark.asyncio
async def test_api_197_version_mismatch(
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
    routes = await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    internal = next(item for item in routes if item["data_classification"] == "Internal")
    route_id = internal["id"]
    assert isinstance(route_id, uuid.UUID)

    await login_as(client)
    response = await client.put(
        f"/api/v1/model-routes/{route_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": 999,
            "task_type": "general",
            "data_classification": "Internal",
            "provider_allowlist": ["openai"],
            "max_cost": 10,
            "require_prompt_version": True,
            "require_structured_output": False,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-VER-001"


@pytest.mark.asyncio
async def test_api_198_connection_test_no_secrets(
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
    routes = await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    internal = next(item for item in routes if item["data_classification"] == "Internal")
    route_id = internal["id"]
    version = internal["version"]
    assert isinstance(route_id, uuid.UUID)
    assert isinstance(version, int)

    await login_as(client)
    response = await client.post(
        f"/api/v1/model-routes/{route_id}/connection-tests",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "reachable" in data
    assert "latency_ms" in data
    serialized = json.dumps(data)
    assert "vault://" not in serialized
    assert "secret" not in serialized.lower()


@pytest.mark.asyncio
async def test_llm_factory_restricted_refused_without_prompt_in_log(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)

    secret_prompt = "TOP_SECRET_PROMPT_TEXT_SHOULD_NOT_APPEAR"
    assert "prompt" not in InvokeInput.__dataclass_fields__
    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-test",
            data_classification="Restricted",
        ),
    )
    await db_session.commit()
    assert output.result == "refused"

    result = await db_session.execute(
        select(AIInvocationLog).where(AIInvocationLog.id == output.log_id)
    )
    row = result.scalar_one()
    mapper = sa_inspect(row).mapper
    serialized = json.dumps(
        {attr.key: getattr(row, attr.key) for attr in mapper.column_attrs},
        default=str,
    )
    assert secret_prompt not in serialized
    assert row.result == "refused"
    assert row.input_ref is None or "redacted://" in (row.input_ref or "")


@pytest.mark.asyncio
async def test_api_184_185_invocation_logs_without_prompt(
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
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-list",
            data_classification="Internal",
        ),
    )
    await db_session.commit()

    await login_as(client)
    list_resp = await client.get("/api/v1/ai-invocation-logs")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert len(items) >= 1
    serialized = json.dumps(items)
    assert "TOP_SECRET" not in serialized
    for item in items:
        assert "prompt" not in item
        assert "prompt_version" in item

    detail_resp = await client.get(f"/api/v1/ai-invocation-logs/{output.log_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["id"] == str(output.log_id)
    assert "prompt" not in detail
    assert "prompt_version" in detail

    missing = await client.get(f"/api/v1/ai-invocation-logs/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_184_tester_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    await seed_tester(db_session, org_id=org_id, project_id=project_id, idp_subject="tester-logs")
    await login_as(client, idp_subject="tester-logs")

    response = await client.get("/api/v1/ai-invocation-logs")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_llm_factory_missing_classification_fail_close_confidential(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
) -> None:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)

    output = await invoke(
        db_session,
        InvokeInput(
            organization_id=org_id,
            user_id=user_id,
            task_type="general",
            prompt_version="v-missing",
            data_classification=None,
        ),
    )
    await db_session.commit()
    assert output.data_classification == "Confidential"
    assert output.result == "refused"

    result = await db_session.execute(
        select(AIInvocationLog).where(AIInvocationLog.id == output.log_id)
    )
    row = result.scalar_one()
    assert row.data_classification == "Confidential"
    assert row.result == "refused"


@pytest.mark.asyncio
async def test_api_197_198_write_audit_and_do_not_invent_credential_ref(
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
    routes = await seed_model_routes(db_session, org_id=org_id, user_id=user_id)
    internal = next(item for item in routes if item["data_classification"] == "Internal")
    route_id = internal["id"]
    version = internal["version"]
    assert isinstance(route_id, uuid.UUID)
    assert isinstance(version, int)

    await login_as(client)
    put_resp = await client.put(
        f"/api/v1/model-routes/{route_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": version,
            "task_type": "general",
            "data_classification": "Internal",
            "provider_allowlist": ["openai"],
            "max_cost": 11,
            "require_prompt_version": True,
            "require_structured_output": False,
            "credential_bound": True,
        },
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["data"]["credential_present"] is False

    db_session.expire_all()
    stored = await db_session.get(ModelRoute, route_id)
    assert stored is not None
    assert stored.credential_ref is None

    test_resp = await client.post(
        f"/api/v1/model-routes/{route_id}/connection-tests",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": version + 1},
    )
    assert test_resp.status_code == 200

    put_audits = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.action == "model_route.put",
            AuditEvent.resource_id == route_id,
        )
    )
    assert put_audits.scalars().first() is not None
    test_audits = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.organization_id == org_id,
            AuditEvent.action == "model_route.connection_test",
            AuditEvent.resource_id == route_id,
        )
    )
    assert test_audits.scalars().first() is not None


@pytest.mark.asyncio
async def test_api_185_197_cross_tenant_404(
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
    await seed_model_routes(db_session, org_id=org_id, user_id=user_id)

    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    foreign_routes = await seed_model_routes(db_session, org_id=other_org, user_id=other_user)
    foreign = foreign_routes[0]
    foreign_id = foreign["id"]
    foreign_version = foreign["version"]
    assert isinstance(foreign_id, uuid.UUID)
    assert isinstance(foreign_version, int)

    foreign_log = await invoke(
        db_session,
        InvokeInput(
            organization_id=other_org,
            user_id=other_user,
            task_type="general",
            prompt_version="v-foreign",
            data_classification="Internal",
        ),
    )
    await db_session.commit()

    await login_as(client)
    put_resp = await client.put(
        f"/api/v1/model-routes/{foreign_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "expected_version": foreign_version,
            "task_type": "general",
            "data_classification": "Internal",
            "provider_allowlist": ["openai"],
            "max_cost": 1,
            "require_prompt_version": True,
            "require_structured_output": False,
        },
    )
    assert put_resp.status_code == 404
    assert put_resp.json()["error"]["code"] == "HT-RES-001"

    log_resp = await client.get(f"/api/v1/ai-invocation-logs/{foreign_log.log_id}")
    assert log_resp.status_code == 404
    assert log_resp.json()["error"]["code"] == "HT-RES-001"
