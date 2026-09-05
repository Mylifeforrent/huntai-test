"""API-026/027/028/212/223 evidence search and export-package tests (S-M2-06)."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.results_evidence import repository as evidence_repo
from app.modules.run_orchestration import command_port as run_command
from tests.helpers import login_as


async def _seed_pending_receipt(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    receipt_id: uuid.UUID,
) -> None:
    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    user_id = seeded_identity["user_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    await run_command.create_command_receipt_for_command(
        db_session,
        receipt_id=receipt_id,
        organization_id=org_id,
        created_at=datetime.now(UTC),
        created_by=user_id,
        command_type="evidence_export",
        status="accepted",
        resource_type="ExportPackage",
        resource_id=receipt_id,
        project_id=project_id,
    )


async def _seed_evidence(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    classifications: list[str],
) -> dict[str, object]:
    org_id = seeded_identity["org_id"]
    user_id = seeded_identity["user_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(user_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)

    from app.modules.run_orchestration.models import TestRun

    now = datetime.now(UTC)
    run = TestRun(
        id=uuid.uuid4(),
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        project_id=project_id,
        env_id=uuid.uuid4(),
        execution_source="script",
        trigger_type="manual",
        idempotency_key=str(uuid.uuid4()),
        status="FAILED",
        snapshot={"case_ids": []},
        result_summary={},
    )
    db_session.add(run)
    await db_session.flush()
    case_result = await evidence_repo.insert_case_result(
        db_session,
        organization_id=org_id,
        created_at=now,
        created_by=user_id,
        test_run_id=run.id,
        test_case_id=uuid.uuid4(),
        test_case_version_id=None,
        attempt_seq=1,
        outcome="failed",
        is_late=False,
        is_partial=False,
        chunk_key=None,
        normalized_summary=None,
        data_classification="Internal",
    )
    evidence_ids: list[str] = []
    for index, classification in enumerate(classifications):
        row = await evidence_repo.insert_evidence_object(
            db_session,
            organization_id=org_id,
            created_at=now,
            created_by=user_id,
            claim=f"claim-{index}-{classification}",
            source_object={
                "connector": "test",
                "resource": f"case-result/{case_result.id}",
                "timestamp": now.isoformat(),
            },
            content_ref=None,
            subject_type="case_result",
            subject_id=case_result.id,
            data_classification=classification,
        )
        evidence_ids.append(str(row.id))
    await db_session.commit()
    return {
        "case_result_id": str(case_result.id),
        "evidence_ids": evidence_ids,
        "project_id": str(project_id),
    }


async def _add_project_member(
    db_session: AsyncSession,
    seeded_identity: dict[str, object],
    *,
    idp_subject: str,
    role: str,
) -> None:
    from app.modules.identity_tenancy.models import ProjectMember, User

    org_id = seeded_identity["org_id"]
    project_id = seeded_identity["project_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(project_id, uuid.UUID)
    now = datetime.now(UTC)
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        organization_id=org_id,
        created_at=now,
        updated_at=now,
        created_by=user_id,
        aggregate_version=1,
        idp_subject=idp_subject,
        display_name=role,
        email=f"{idp_subject}@example.com",
        is_disabled=False,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        ProjectMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
            created_by=user.id,
            aggregate_version=1,
            project_id=project_id,
            user_id=user_id,
            role=role,
        )
    )
    await db_session.commit()


def _export_body(evidence_ids: list[str], *, fmt: str = "zip") -> dict[str, object]:
    return {"format": fmt, "evidence_object_ids": evidence_ids}


@pytest.mark.asyncio
async def test_api_026_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await _seed_evidence(db_session, seeded_identity, classifications=["Internal", "Confidential"])
    await login_as(client)
    response = await client.get("/api/v1/evidence-objects")
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 2
    first = items[0]
    assert first["claim"].startswith("claim-")
    assert first["source_object"]["connector"] == "test"
    assert first["subject_type"] == "case_result"
    assert first["data_classification"] in {"Internal", "Confidential"}
    assert "presign" not in str(first).lower()


@pytest.mark.asyncio
async def test_api_026_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    _ = seeded_identity
    response = await client.get("/api/v1/evidence-objects")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_026_subject_pair_required(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.get(
        "/api/v1/evidence-objects",
        params={"subject_id": str(uuid.uuid4())},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "HT-VAL-001"


@pytest.mark.asyncio
async def test_api_027_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    detail = await client.get(f"/api/v1/evidence-objects/{evidence_ids[0]}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == evidence_ids[0]
    missing = await client.get(f"/api/v1/evidence-objects/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_028_0223_export_zip_happy_path(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(
        db_session, seeded_identity, classifications=["Internal", "Confidential"]
    )
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    accepted = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_export_body(evidence_ids),
    )
    assert accepted.status_code == 202, accepted.text
    receipt = accepted.json()["data"]
    receipt_id = receipt["id"]
    assert receipt["command_type"] == "evidence_export"
    assert receipt["status"] == "accepted"
    assert receipt["poll"]["sse_path"] == f"/api/v1/command-receipts/{receipt_id}/events"

    # 受理 ≠ 完成：权威完成以回执 + API-223 可授权取得为准
    status = await client.get(f"/api/v1/command-receipts/{receipt_id}")
    assert status.status_code == 200
    assert status.json()["data"]["status"] == "succeeded"

    download = await client.get(f"/api/v1/export-packages/{receipt_id}/content")
    assert download.status_code == 200
    assert "attachment" in download.headers.get("content-disposition", "")
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        evidence_entries = [name for name in names if name.startswith("evidence/")]
        assert len(evidence_entries) == len(evidence_ids)


@pytest.mark.asyncio
async def test_api_028_md_and_json_formats(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    for fmt in ("md", "json"):
        accepted = await client.post(
            "/api/v1/evidence-objects/export-packages",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json=_export_body(evidence_ids, fmt=fmt),
        )
        assert accepted.status_code == 202, accepted.text
        receipt_id = accepted.json()["data"]["id"]
        download = await client.get(f"/api/v1/export-packages/{receipt_id}/content")
        assert download.status_code == 200
        assert b"claim-0-Internal" in download.content


@pytest.mark.asyncio
async def test_api_028_idempotent_replay(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    key = str(uuid.uuid4())
    first = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": key},
        json=_export_body(evidence_ids),
    )
    assert first.status_code == 202
    replay = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": key},
        json=_export_body(evidence_ids),
    )
    assert replay.status_code == 202
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    conflict = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": key},
        json=_export_body(evidence_ids, fmt="json"),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "HT-IDEM-001"


@pytest.mark.asyncio
async def test_api_028_viewer_forbidden(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    await _add_project_member(
        db_session, seeded_identity, idp_subject="viewer-subject", role="viewer"
    )
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client, idp_subject="viewer-subject")
    response = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_export_body(evidence_ids),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-IAM-001"


@pytest.mark.asyncio
async def test_api_028_restricted_policy_deny(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(
        db_session, seeded_identity, classifications=["Internal", "Restricted"]
    )
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    response = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_export_body(evidence_ids),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HT-POL-001"


@pytest.mark.asyncio
async def test_api_028_unknown_evidence(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_export_body([str(uuid.uuid4())]),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HT-RES-001"


@pytest.mark.asyncio
async def test_api_223_not_completed_state(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    await login_as(client)
    receipt_id = uuid.uuid4()
    await _seed_pending_receipt(db_session, seeded_identity, receipt_id)
    await db_session.commit()
    response = await client.get(f"/api/v1/export-packages/{receipt_id}/content")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HT-STATE-001"


@pytest.mark.asyncio
async def test_api_223_unauthenticated(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
) -> None:
    _ = seeded_identity
    response = await client.get(f"/api/v1/export-packages/{uuid.uuid4()}/content")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "HT-AUTH-001"


@pytest.mark.asyncio
async def test_api_212_sse_terminal_frame(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    seeded = await _seed_evidence(db_session, seeded_identity, classifications=["Internal"])
    evidence_ids = seeded["evidence_ids"]
    assert isinstance(evidence_ids, list)
    await login_as(client)
    accepted = await client.post(
        "/api/v1/evidence-objects/export-packages",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=_export_body(evidence_ids),
    )
    receipt_id = accepted.json()["data"]["id"]
    async with client.stream("GET", f"/api/v1/command-receipts/{receipt_id}/events") as events:
        assert events.status_code == 200
        assert "text/event-stream" in events.headers.get("content-type", "")
        body = ""
        async for line in events.aiter_lines():
            body += line + "\n"
    assert "event: resource_changed" in body
    assert "status_may_have_changed" in body
    assert "command" not in body.split("event: ")[0]


@pytest.mark.asyncio
async def test_api_212_unknown_receipt(
    client: AsyncClient,
    seeded_identity: dict[str, object],
    db_session: AsyncSession,
    mock_oidc_token_exchange: object,
) -> None:
    _ = mock_oidc_token_exchange
    await login_as(client)
    response = await client.get(
        f"/api/v1/command-receipts/{uuid.uuid4()}/events",
    )
    assert response.status_code == 404
