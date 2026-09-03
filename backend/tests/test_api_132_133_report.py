"""API-132/133 and evidence_refs on triage for S-M1-04."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import login_as
from tests.test_api_120_action_previews import _seed_viewer
from tests.test_api_130_131_039_heal import _start_failed_run
from tests.test_api_170_172_api_tokens import _issue_body


@pytest.mark.asyncio
async def test_api_132_happy_path_updates_category_and_history(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    old_category = report["items"][0]["category"]
    idem = str(uuid.uuid4())
    patch = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": idem},
        json={
            "corrections": [
                {"field": "category", "old": old_category, "new": "flaky"},
            ]
        },
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["category"] == "flaky"
    assert len(patch.json()["data"]["correction_history"]) == 1

    detail = await client.get(f"/api/v1/failure-clusters/{cluster_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["category"] == "flaky"
    assert detail.json()["data"]["correction_history"][0]["field"] == "category"


@pytest.mark.asyncio
async def test_api_132_idempotent_replay(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    idem = str(uuid.uuid4())
    body = {"corrections": [{"field": "blocking_judgment", "new": "blocker"}]}
    first = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": idem},
        json=body,
    )
    second = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": idem},
        json=body,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_api_132_old_mismatch_validation(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    response = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "corrections": [
                {"field": "category", "old": "flaky", "new": "unknown"},
            ]
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"
    detail = await client.get(f"/api/v1/failure-clusters/{cluster_id}")
    assert detail.json()["data"]["category"] == report["items"][0]["category"]
    assert detail.json()["data"]["correction_history"] == []


@pytest.mark.asyncio
async def test_api_132_batch_second_invalid_does_not_apply_first(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    original_category = report["items"][0]["category"]
    response = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "corrections": [
                {"field": "category", "new": "flaky"},
                {"field": "blocking_judgment", "old": "blocker", "new": "non_blocker"},
            ]
        },
    )
    assert response.status_code == 400
    detail = await client.get(f"/api/v1/failure-clusters/{cluster_id}")
    assert detail.json()["data"]["category"] == original_category
    assert detail.json()["data"]["correction_history"] == []


@pytest.mark.asyncio
async def test_api_132_viewer_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await _seed_viewer(
        db_session,
        org_id=seeded_identity["org_id"],  # type: ignore[arg-type]
        project_id=project_id,
        idp_subject="viewer-132",
    )
    await login_as(client, idp_subject="viewer-132")
    response = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"corrections": [{"field": "category", "new": "flaky"}]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_132_token_returns_401(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    token_resp = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["read"]),
    )
    token = token_resp.json()["data"]["token"]
    client.cookies.clear()
    response = await client.patch(
        f"/api/v1/failure-clusters/{cluster_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        json={"corrections": [{"field": "category", "new": "flaky"}]},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_133_token_returns_401(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(project_id, uuid.UUID)
    await login_as(client)
    token_resp = await client.post(
        "/api/v1/api-tokens",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_issue_body(project_id=project_id, scopes=["read"]),
    )
    token = token_resp.json()["data"]["token"]
    client.cookies.clear()
    response = await client.get(
        f"/api/v1/failure-clusters/{cluster_id}/similar",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_api_132_133_cross_tenant_not_found(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    from app.modules.identity_tenancy.models import (
        DEFAULT_CAPABILITY_CONTROLS,
        DEFAULT_SIEM_EXPORT,
        Organization,
        Project,
        User,
    )
    from app.modules.results_evidence import repository as evidence_repo
    from app.modules.run_orchestration import repository as run_repo

    now = datetime.now(UTC)
    other_org = uuid.uuid4()
    other_user = uuid.uuid4()
    other_project = uuid.uuid4()
    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Other Org 132",
            slug="other-org-132",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            siem_export=dict(DEFAULT_SIEM_EXPORT),
            is_active=True,
        )
    )
    await db_session.flush()
    db_session.add(
        User(
            id=other_user,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            idp_subject="other-132-subject",
            display_name="Other",
            email="other-132@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=other_project,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=other_user,
            aggregate_version=1,
            name="Other Project 132",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    foreign_run = await run_repo.create_test_run(
        db_session,
        organization_id=other_org,
        created_at=now,
        created_by=other_user,
        project_id=other_project,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={
            "case_ids": [],
            "env_id": str(uuid.uuid4()),
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    other_cluster = await evidence_repo.insert_failure_cluster(
        db_session,
        organization_id=other_org,
        created_at=now,
        created_by=other_user,
        test_run_id=foreign_run.id,
        category="env_down",
        root_cause="x",
        confidence=0.3,
        blocking_judgment="uncertain",
        evidence_refs=[],
        failure_refs=[],
        unclustered_refs=None,
        fixes=None,
    )
    await db_session.commit()
    await login_as(client)
    patch = await client.patch(
        f"/api/v1/failure-clusters/{other_cluster.id}",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"corrections": [{"field": "category", "new": "flaky"}]},
    )
    assert patch.status_code == 404
    assert patch.json()["error"]["code"] == "HT-RES-001"
    similar = await client.get(f"/api/v1/failure-clusters/{other_cluster.id}/similar")
    assert similar.status_code == 404
    assert similar.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_133_empty_list(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    cluster_id = report["items"][0]["id"]
    response = await client.get(f"/api/v1/failure-clusters/{cluster_id}/similar")
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_api_133_similar_same_project_and_score(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange

    from app.modules.results_evidence import repository as evidence_repo
    from app.modules.run_orchestration import repository as run_repo

    project_id = seeded_identity["project_id"]
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)

    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    source_id = uuid.UUID(str(report["items"][0]["id"]))
    source_category = report["items"][0]["category"]
    now = datetime.now(UTC)

    same_run = await run_repo.create_test_run(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        project_id=project_id,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={
            "case_ids": [],
            "env_id": str(uuid.uuid4()),
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    match_cluster = await evidence_repo.insert_failure_cluster(
        db_session,
        organization_id=org_id,
        created_at=now + timedelta(seconds=1),
        created_by=user_id,
        test_run_id=same_run.id,
        category=source_category,
        root_cause="peer",
        confidence=0.5,
        blocking_judgment=report["items"][0]["blocking_judgment"],
        evidence_refs=[],
        failure_refs=[],
        unclustered_refs=None,
        fixes=None,
    )
    diff_blocking = await evidence_repo.insert_failure_cluster(
        db_session,
        organization_id=org_id,
        created_at=now + timedelta(seconds=2),
        created_by=user_id,
        test_run_id=same_run.id,
        category=source_category,
        root_cause="peer2",
        confidence=0.5,
        blocking_judgment="blocker",
        evidence_refs=[],
        failure_refs=[],
        unclustered_refs=None,
        fixes=None,
    )

    other_org = uuid.uuid4()
    other_project = uuid.uuid4()
    from app.modules.identity_tenancy.models import (
        DEFAULT_CAPABILITY_CONTROLS,
        DEFAULT_SIEM_EXPORT,
        Organization,
        Project,
        User,
    )

    db_session.add(
        Organization(
            id=other_org,
            created_at=now,
            updated_at=now,
            created_by=None,
            aggregate_version=1,
            name="Peer Org",
            slug="peer-org-133",
            capability_controls=dict(DEFAULT_CAPABILITY_CONTROLS),
            siem_export=dict(DEFAULT_SIEM_EXPORT),
            is_active=True,
        )
    )
    await db_session.flush()
    peer_user = uuid.uuid4()
    db_session.add(
        User(
            id=peer_user,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=peer_user,
            aggregate_version=1,
            idp_subject="peer-user-133",
            display_name="Peer",
            email="peer-133@example.com",
            is_disabled=False,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=other_project,
            organization_id=other_org,
            created_at=now,
            updated_at=now,
            created_by=peer_user,
            aggregate_version=1,
            name="Peer Project",
            jira_project_key=None,
            jira_sync_cursor=None,
            bind_env_ids=None,
        )
    )
    await db_session.flush()
    other_run = await run_repo.create_test_run(
        db_session,
        organization_id=other_org,
        created_at=now,
        created_by=peer_user,
        project_id=other_project,
        plan_id=None,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={
            "case_ids": [],
            "env_id": str(uuid.uuid4()),
            "env_config_version": 1,
            "params_redacted": {},
        },
    )
    await evidence_repo.insert_failure_cluster(
        db_session,
        organization_id=other_org,
        created_at=now,
        created_by=peer_user,
        test_run_id=other_run.id,
        category=source_category,
        root_cause="other project",
        confidence=0.5,
        blocking_judgment="blocker",
        evidence_refs=[],
        failure_refs=[],
        unclustered_refs=None,
        fixes=None,
    )
    await db_session.commit()

    await login_as(client)
    response = await client.get(f"/api/v1/failure-clusters/{source_id}/similar")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    ids = {item["id"] for item in items}
    assert str(match_cluster.id) in ids
    assert str(diff_blocking.id) in ids
    scores = {item["id"]: item["similarity_score"] for item in items}
    assert scores[str(match_cluster.id)] == 1.0
    assert scores[str(diff_blocking.id)] == 0.7


@pytest.mark.asyncio
async def test_failed_run_clusters_have_evidence_refs(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    _run, report = await _start_failed_run(client, db_session, seeded_identity)
    assert report["items"]
    for item in report["items"]:
        assert item["evidence_refs"], "expected EvidenceObject IDs on clusters"
