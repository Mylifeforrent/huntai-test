from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance import query_port as ai_query
from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.execution_registry import query_port as execution_query
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.results_evidence import query_port as evidence_query
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event
from app.modules.run_orchestration import query_port as run_query
from app.modules.test_assets import repository as repo
from app.modules.test_assets.locator_health import extract_locator_health_from_steps
from app.modules.test_assets.models import ImportSource, TestCase, TestCaseVersion, TestPlan

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})
REVIEW_ROLES = frozenset({"owner", "admin"})

COMMAND_IMPORT_REGISTER = "import_source.register"
COMMAND_CREATE_DRAFT = "test_case.create_draft"
COMMAND_PATCH_DRAFT = "test_case.patch_draft"
COMMAND_SUBMIT_REVIEW = "test_case.submit_review"
COMMAND_REVIEW = "test_case.review"
COMMAND_ROLLBACK = "test_case.rollback_pointer"

COMMAND_PLAN_CREATE = "test_plan.create"
COMMAND_PLAN_PATCH = "test_plan.patch"
COMMAND_PLAN_PUT_CASE_IDS = "test_plan.put_case_ids"
COMMAND_PLAN_PUT_SCHEDULE = "test_plan.put_schedule"

ROLLBACK_ROLES = frozenset({"owner", "admin"})

VALID_CASE_TYPES = frozenset({"api", "web", "performance", "referenced"})
VALID_EXECUTION_MODES = frozenset({"script", "agent"})
VALID_PRIORITIES = frozenset({"P0", "P1", "P2", "P3"})
VALID_LIFECYCLE = frozenset({"DRAFT", "PENDING_REVIEW", "ACTIVE", "DEPRECATED"})
VALID_SOURCE_TYPES = frozenset({"openapi", "postman", "curl"})

RESTRICTED_MARKERS = (
    "BEGIN RSA PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _detect_classification(content: str) -> str:
    for marker in RESTRICTED_MARKERS:
        if marker in content:
            return "Restricted"
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            explicit = data.get("data_classification")
            if explicit == "Restricted":
                return "Restricted"
    except json.JSONDecodeError:
        pass
    return "Confidential"


def _content_has_restricted(payload: Any) -> bool:
    text = json.dumps(payload) if not isinstance(payload, str) else payload
    restricted_marker = '"data_classification":"Restricted"'
    return any(marker in text for marker in RESTRICTED_MARKERS) or restricted_marker in text


async def _require_project_role(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    allowed: frozenset[str],
) -> str:
    if not await identity_query.project_exists_in_org(
        session, organization_id=ctx.organization.id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None or role not in allowed:
        if role is None:
            raise ValueError("not_found")
        raise ValueError("forbidden")
    return role


def serialize_list_item(row: TestCase) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "case_type": row.case_type,
        "execution_mode": row.execution_mode,
        "title": row.title,
        "priority": row.priority,
        "tags": list(row.tags),
        "lifecycle_status": row.lifecycle_status,
        "validity": row.validity,
        "version": row.aggregate_version,
        "current_version_id": str(row.current_version_id) if row.current_version_id else None,
        "jira_story_key": row.jira_story_key,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _fix_confidence(fix: dict[str, Any]) -> float:
    try:
        return float(fix.get("confidence", 0.0))
    except (TypeError, ValueError):  # fmt: skip
        return 0.0


def _overlay_locator_health(
    locator_health: list[dict[str, Any]],
    *,
    cluster: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not locator_health:
        return locator_health
    fixes_by_locator: dict[str, dict[str, Any]] = {}
    cluster_id: str | None = None
    stale_cluster = cluster is not None and cluster.get("category") == "locator_stale"
    if stale_cluster and cluster is not None:
        cluster_id = str(cluster["id"])
        for cluster_fix in cluster.get("fixes") or []:
            if not isinstance(cluster_fix, dict) or cluster_fix.get("field") != "locator_health":
                continue
            locator_id = cluster_fix.get("locator_id")
            if isinstance(locator_id, str) and locator_id:
                fixes_by_locator[locator_id] = cluster_fix
        matched = any(str(loc.get("locator_id", "")) in fixes_by_locator for loc in locator_health)
        if fixes_by_locator and not matched:
            primary = next(
                (loc for loc in locator_health if loc.get("is_primary") is True),
                locator_health[0],
            )
            primary_id = str(primary.get("locator_id", ""))
            if primary_id:
                fixes_by_locator[primary_id] = next(iter(fixes_by_locator.values()))

    overlaid: list[dict[str, Any]] = []
    for loc in locator_health:
        item = dict(loc)
        locator_id = str(item.get("locator_id", ""))
        fix = fixes_by_locator.get(locator_id)
        if fix and _fix_confidence(fix) >= 0.7:
            item["health"] = "stale"
            item["expression"] = str(fix.get("current", item.get("expression", "")))
            item["failure_cluster_id"] = cluster_id
            item["fix_preview"] = {
                "field": str(fix.get("field", "")),
                "current": str(fix.get("current", "")),
                "suggested": str(fix.get("suggested", "")),
                "reason": str(fix.get("reason", "")),
                "confidence": _fix_confidence(fix),
            }
            candidates = fix.get("candidates")
            if isinstance(candidates, list):
                item["candidates"] = candidates
            note = fix.get("semantic_invariant_note")
            if isinstance(note, str) and note:
                item["semantic_invariant_note"] = note
        elif fix or stale_cluster:
            item["health"] = "stale"
            if cluster_id:
                item["failure_cluster_id"] = cluster_id
            if fix:
                for extra_key in ("human_repair_hint", "dom_diff", "semantic_invariant_note"):
                    extra = fix.get(extra_key)
                    if isinstance(extra, str) and extra:
                        item[extra_key] = extra
                candidates = fix.get("candidates")
                if isinstance(candidates, list):
                    item["candidates"] = candidates
        else:
            item["health"] = "ok"
        overlaid.append(item)
    return overlaid


def serialize_detail(row: TestCase, version: TestCaseVersion | None) -> dict[str, Any]:
    payload = serialize_list_item(row)
    payload["version"] = row.aggregate_version
    if version is not None:
        snapshot = version.snapshot
        payload["steps"] = snapshot.get("steps", [])
        payload["assertions"] = snapshot.get("assertions", [])
        payload["locator_health"] = snapshot.get("locator_health", [])
    else:
        payload["steps"] = []
        payload["assertions"] = []
        payload["locator_health"] = []
    return payload


def _build_snapshot(
    *,
    title: str,
    priority: str,
    tags: list[str],
    case_type: str,
    execution_mode: str,
    drafts: list[dict[str, Any]] | None,
    script: str | None,
) -> dict[str, Any]:
    steps: list[Any] = []
    assertions: list[Any] = []
    if drafts:
        for draft in drafts:
            draft_steps = draft.get("steps")
            if isinstance(draft_steps, list):
                steps.extend(draft_steps)
            draft_assertions = draft.get("assertions")
            if isinstance(draft_assertions, list):
                assertions.extend(draft_assertions)
    elif script:
        steps = [{"action": "script", "params": {"ref": "inline"}}]
    locator_health: list[dict[str, Any]] = []
    if case_type == "web":
        locator_health = extract_locator_health_from_steps(steps)
    return {
        "title": title,
        "priority": priority,
        "tags": tags,
        "case_type": case_type,
        "execution_mode": execution_mode,
        "steps": steps,
        "assertions": assertions,
        "locator_health": locator_health,
    }


def _modification_amplitude(staged: list[dict[str, Any]], saved: list[dict[str, Any]]) -> float:
    if not staged:
        return 0.0
    if not saved:
        return 1.0
    staged_json = json.dumps(staged, sort_keys=True)
    saved_json = json.dumps(saved, sort_keys=True)
    if staged_json == saved_json:
        return 0.0
    max_len = max(len(staged_json), len(saved_json))
    if max_len == 0:
        return 0.0
    diff = sum(1 for a, b in zip(staged_json, saved_json, strict=False) if a != b)
    diff += abs(len(staged_json) - len(saved_json))
    return min(1.0, diff / max_len)


@dataclass(frozen=True)
class TestCaseCreateInput:
    project_id: uuid.UUID
    case_type: str
    execution_mode: str
    title: str
    generation_id: uuid.UUID | None = None
    priority: str | None = None
    tags: list[str] | None = None
    drafts: list[dict[str, Any]] | None = None
    job_binding: dict[str, Any] | None = None
    jira_story_key: str | None = None
    script: str | None = None


@dataclass(frozen=True)
class TestCasePatchInput:
    expected_version: int
    title: str | None = None
    priority: str | None = None
    tags: list[str] | None = None
    drafts: list[dict[str, Any]] | None = None
    job_binding: dict[str, Any] | None = None
    jira_story_key: str | None = None
    script: str | None = None


async def list_test_cases_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    cursor: str | None = None,
    limit: int | None = None,
    lifecycle_status: str | None = None,
    validity: str | None = None,
    tags: str | None = None,
    case_type: str | None = None,
    execution_mode: str | None = None,
    priority: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=project_id, allowed=READ_ROLES)
    page_limit = min(limit or 50, 100)
    cursor_updated_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_updated_at, cursor_id = repo.decode_updated_id_cursor(cursor)
    rows = await repo.list_test_cases(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        lifecycle_status=lifecycle_status,
        validity=validity,
        tags=tags,
        case_type=case_type,
        execution_mode=execution_mode,
        priority=priority,
        q=q,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
        limit=page_limit,
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = repo.encode_updated_id_cursor(updated_at=last.updated_at, item_id=last.id)
    return {
        "items": [serialize_list_item(row) for row in items],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_test_case_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session, organization_id=ctx.organization.id, test_case_id=test_case_id
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    version = None
    if row.current_version_id is not None:
        version = await repo.get_test_case_version(
            session,
            organization_id=ctx.organization.id,
            version_id=row.current_version_id,
        )
    payload = serialize_detail(row, version)
    payload["evidence_preview"] = await evidence_query.get_evidence_preview_for_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
    )
    locator_health = payload.get("locator_health", [])
    if isinstance(locator_health, list) and not locator_health:
        steps = payload.get("steps", [])
        if isinstance(steps, list) and row.case_type == "web":
            locator_health = extract_locator_health_from_steps(steps)
    cluster = await evidence_query.get_latest_locator_stale_cluster_for_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
    )
    if isinstance(locator_health, list):
        payload["locator_health"] = _overlay_locator_health(locator_health, cluster=cluster)
    if cluster is not None:
        payload["locator_stale_cluster_confidence"] = float(cluster["confidence"])
    return payload


async def register_import_source_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    source_type: str,
    inline_content: str | None,
    object_key: str | None,
    original_filename: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_IMPORT_REGISTER,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if object_key:
        raise ValueError("file_validation")
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError("validation")
    content = inline_content or ""
    if not content.strip():
        raise ValueError("validation")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("file_validation") from exc
    stripped = content.lstrip()
    if stripped.startswith(("---", "openapi:", "swagger:")):
        raise ValueError("file_validation")
    if source_type in {"openapi", "postman"}:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("file_validation") from exc
        if not isinstance(parsed, dict):
            raise ValueError("file_validation")
    classification = _detect_classification(content)
    if classification == "Restricted":
        raise ValueError("policy")
    now = datetime.now(UTC)
    source_id = uuid.uuid4()
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    row = ImportSource(
        id=source_id,
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        aggregate_version=1,
        project_id=project_id,
        source_type=source_type,
        original_filename=original_filename,
        byte_size=len(content.encode("utf-8")),
        checksum=checksum,
        data_classification=classification,
        content_text=content,
    )
    await repo.insert_import_source(session, row)
    response = {
        "id": str(source_id),
        "source_type": source_type,
        "project_id": str(project_id),
        "original_filename": original_filename,
        "data_classification": classification,
        "byte_size": row.byte_size,
    }
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_IMPORT_REGISTER,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref={"data": response},
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="import_source.register",
            resource_type="import_source",
            resource_id=source_id,
            project_id=project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return {"data": response}


async def get_import_source_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    source_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_import_source(
        session, organization_id=ctx.organization.id, source_id=source_id
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    return {
        "source_type": row.source_type,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "data_classification": row.data_classification,
        "created_at": _iso(row.created_at),
    }


def _validate_referenced_case_fields(
    *,
    case_type: str,
    execution_mode: str,
    script_ref: str | None,
    job_binding: dict[str, Any] | None,
) -> None:
    if case_type == "referenced":
        if script_ref and script_ref.strip():
            raise ValueError("validation")
        if job_binding is None or not isinstance(job_binding, dict):
            raise ValueError("validation")
        job_id = job_binding.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("validation")
        if execution_mode != "script":
            raise ValueError("validation")


async def create_test_case_draft_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: TestCaseCreateInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=body.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE_DRAFT,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if body.case_type not in VALID_CASE_TYPES:
        raise ValueError("validation")
    if body.execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError("validation")
    _validate_referenced_case_fields(
        case_type=body.case_type,
        execution_mode=body.execution_mode,
        script_ref=body.script,
        job_binding=body.job_binding,
    )
    priority = body.priority or "P2"
    if priority not in VALID_PRIORITIES:
        raise ValueError("validation")

    drafts = list(body.drafts) if body.drafts else None
    if body.generation_id is not None and drafts is None:
        gen = await ai_query.get_generation_drafts(
            session,
            organization_id=ctx.organization.id,
            generation_id=body.generation_id,
            project_id=body.project_id,
        )
        if gen is None:
            raise ValueError("not_found")
        drafts = gen.get("cases", [])

    if _content_has_restricted(body.script) or _content_has_restricted(drafts):
        raise ValueError("policy")

    tags = list(body.tags or [])
    if body.generation_id is not None and "ai-generated" not in tags:
        tags.append("ai-generated")

    now = datetime.now(UTC)
    case_id = uuid.uuid4()
    version_id = uuid.uuid4()
    snapshot = _build_snapshot(
        title=body.title,
        priority=priority,
        tags=tags,
        case_type=body.case_type,
        execution_mode=body.execution_mode,
        drafts=drafts,
        script=body.script,
    )
    row = TestCase(
        id=case_id,
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        aggregate_version=1,
        project_id=body.project_id,
        case_type=body.case_type,
        execution_mode=body.execution_mode,
        title=body.title,
        priority=priority,
        tags=tags,
        lifecycle_status="DRAFT",
        validity="valid",
        invalid_reason=None,
        invalidated_at=None,
        script_ref=body.script,
        job_binding=body.job_binding,
        jira_story_key=body.jira_story_key,
        current_version_id=version_id,
    )
    version_row = TestCaseVersion(
        id=version_id,
        organization_id=ctx.organization.id,
        created_at=now,
        created_by=ctx.user.id,
        test_case_id=case_id,
        version_seq=1,
        snapshot=snapshot,
        data_classification="Confidential",
    )
    await repo.insert_test_case(session, row)
    await repo.insert_test_case_version(session, version_row)

    if body.generation_id is not None:
        staged = await ai_query.get_generation_drafts(
            session,
            organization_id=ctx.organization.id,
            generation_id=body.generation_id,
            project_id=body.project_id,
        )
        staged_cases = staged.get("cases", []) if staged else []
        saved_cases = drafts or []
        adopted = 1 if saved_cases else 0
        discarded = max(0, len(staged_cases) - adopted)
        amplitude = _modification_amplitude(staged_cases, saved_cases)
        modified = 1 if amplitude > 0 else 0
        await invoke(
            session,
            InvokeInput(
                organization_id=ctx.organization.id,
                user_id=ctx.user.id,
                task_type="general",
                prompt_version="a1.adopt.v1",
                capability_id="A1",
                data_classification="Confidential",
                usage_metadata={
                    "adopted": adopted,
                    "modified": modified,
                    "discarded": discarded,
                    "modification_amplitude": amplitude,
                },
            ),
        )

    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_CREATE_DRAFT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_case.create_draft",
            resource_type="test_case",
            resource_id=case_id,
            project_id=body.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def patch_test_case_draft_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    body: TestCasePatchInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PATCH_DRAFT,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.lifecycle_status != "DRAFT":
        raise ValueError("state")
    if row.aggregate_version != body.expected_version:
        raise ValueError("version")

    next_script = body.script if body.script is not None else row.script_ref
    next_binding = body.job_binding if body.job_binding is not None else row.job_binding
    _validate_referenced_case_fields(
        case_type=row.case_type,
        execution_mode=row.execution_mode,
        script_ref=next_script,
        job_binding=next_binding if isinstance(next_binding, dict) else None,
    )

    if _content_has_restricted(body.drafts) or _content_has_restricted(body.script):
        raise ValueError("policy")

    now = datetime.now(UTC)
    version_id = uuid.uuid4()
    current_version = None
    if row.current_version_id is not None:
        current_version = await repo.get_test_case_version(
            session,
            organization_id=ctx.organization.id,
            version_id=row.current_version_id,
        )
    prev_snapshot = current_version.snapshot if current_version else {}
    title = body.title if body.title is not None else row.title
    priority = body.priority if body.priority is not None else row.priority
    tags = list(body.tags) if body.tags is not None else list(row.tags)
    drafts = body.drafts
    script = body.script if body.script is not None else row.script_ref
    snapshot = _build_snapshot(
        title=title,
        priority=priority,
        tags=tags,
        case_type=row.case_type,
        execution_mode=row.execution_mode,
        drafts=drafts if drafts is not None else [prev_snapshot],
        script=script,
    )
    next_seq = (current_version.version_seq + 1) if current_version else 1
    version_row = TestCaseVersion(
        id=version_id,
        organization_id=ctx.organization.id,
        created_at=now,
        created_by=ctx.user.id,
        test_case_id=test_case_id,
        version_seq=next_seq,
        snapshot=snapshot,
        data_classification="Confidential",
    )
    row.title = title
    row.priority = priority
    row.tags = tags
    if body.job_binding is not None:
        row.job_binding = body.job_binding
    if body.jira_story_key is not None:
        row.jira_story_key = body.jira_story_key
    if body.script is not None:
        row.script_ref = body.script
    row.current_version_id = version_id
    row.aggregate_version += 1
    row.updated_at = now
    await repo.insert_test_case_version(session, version_row)

    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PATCH_DRAFT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


async def submit_review_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    expected_version: int,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_SUBMIT_REVIEW,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.lifecycle_status != "DRAFT":
        raise ValueError("state")
    if row.aggregate_version != expected_version:
        raise ValueError("version")

    now = datetime.now(UTC)
    row.lifecycle_status = "PENDING_REVIEW"
    row.aggregate_version += 1
    row.updated_at = now
    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_SUBMIT_REVIEW,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


async def review_test_case_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    expected_version: int,
    decision: str,
    jira_story_key: str | None,
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=REVIEW_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_REVIEW,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.lifecycle_status != "PENDING_REVIEW":
        raise ValueError("state")
    if row.aggregate_version != expected_version:
        raise ValueError("version")
    if decision not in {"approve", "reject"}:
        raise ValueError("validation")

    now = datetime.now(UTC)
    if decision == "approve":
        row.lifecycle_status = "ACTIVE"
    else:
        row.lifecycle_status = "DRAFT"
    if jira_story_key is not None:
        row.jira_story_key = jira_story_key
    row.aggregate_version += 1
    row.updated_at = now
    _ = reason
    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_REVIEW,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action=f"test_case.review.{decision}",
            resource_type="test_case",
            resource_id=test_case_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def rollback_test_case_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    expected_version: int,
    target_version_id: uuid.UUID,
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=ROLLBACK_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_ROLLBACK,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.aggregate_version != expected_version:
        raise ValueError("version")
    target_version = await repo.get_test_case_version(
        session,
        organization_id=ctx.organization.id,
        version_id=target_version_id,
    )
    if target_version is None or target_version.test_case_id != test_case_id:
        raise ValueError("state")

    now = datetime.now(UTC)
    row.current_version_id = target_version_id
    row.updated_at = now
    row.aggregate_version += 1
    await session.flush()
    response = {"data": serialize_list_item(row)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_ROLLBACK,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_case.rollback_pointer",
            resource_type="test_case",
            resource_id=test_case_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    _ = reason
    return response


def _serialize_schedule_binding(binding: dict[str, Any] | None) -> dict[str, Any] | None:
    if binding is None:
        return None
    payload: dict[str, Any] = {}
    if "enabled" in binding:
        payload["enabled"] = binding["enabled"]
    if "schedule" in binding:
        payload["schedule"] = binding["schedule"]
    if "env_id" in binding and binding["env_id"] is not None:
        payload["env_id"] = str(binding["env_id"])
    return payload


def serialize_plan_list_item(row: TestPlan, *, case_count: int) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "name": row.name,
        "jira_fix_version": row.jira_fix_version,
        "case_count": case_count,
        "version": row.aggregate_version,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def serialize_plan_write(row: TestPlan, *, case_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "name": row.name,
        "jira_fix_version": row.jira_fix_version,
        "version": row.aggregate_version,
        "case_ids": [str(case_id) for case_id in case_ids],
    }


async def _serialize_plan_detail(
    session: AsyncSession,
    ctx: SessionContext,
    row: TestPlan,
) -> dict[str, Any]:
    case_ids = await repo.list_plan_case_ids(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=row.id,
    )
    latest_run = await run_query.get_latest_run_for_plan(
        session,
        organization_id=ctx.organization.id,
        plan_id=row.id,
    )
    report_aggregate: dict[str, Any] = {
        "last_run_id": None,
        "last_run_status": None,
        "pass_rate": None,
        "gate_result": None,
    }
    if latest_run is not None:
        report_aggregate["last_run_id"] = str(latest_run["id"])
        report_aggregate["last_run_status"] = latest_run["status"]
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "name": row.name,
        "jira_fix_version": row.jira_fix_version,
        "case_ids": [str(case_id) for case_id in case_ids],
        "schedule": _serialize_schedule_binding(row.schedule_binding),
        "report_aggregate": report_aggregate,
        "version": row.aggregate_version,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "created_by": str(row.created_by) if row.created_by else None,
    }


@dataclass(frozen=True)
class TestPlanCreateInput:
    project_id: uuid.UUID
    name: str
    jira_fix_version: str | None = None


@dataclass(frozen=True)
class TestPlanPatchInput:
    expected_version: int
    name: str | None = None
    jira_fix_version: str | None = None


@dataclass(frozen=True)
class TestPlanCaseIdsInput:
    expected_version: int
    case_ids: list[uuid.UUID]


@dataclass(frozen=True)
class TestPlanScheduleInput:
    expected_version: int
    enabled: bool | None = None
    schedule: dict[str, Any] | None = None
    env_id: uuid.UUID | None = None


async def list_test_plans_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    cursor: str | None = None,
    limit: int | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=project_id, allowed=READ_ROLES)
    page_limit = min(limit or 50, 100)
    cursor_updated_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_updated_at, cursor_id = repo.decode_updated_id_cursor(cursor)
    rows = await repo.list_test_plans(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        q=q,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
        limit=page_limit,
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more and items:
        last_plan, _ = items[-1]
        next_cursor = repo.encode_updated_id_cursor(
            updated_at=last_plan.updated_at,
            item_id=last_plan.id,
        )
    return {
        "items": [serialize_plan_list_item(plan, case_count=count) for plan, count in items],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_test_plan_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_plan_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_test_plan(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    return await _serialize_plan_detail(session, ctx, row)


async def _validate_case_ids_for_plan(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    case_ids: list[uuid.UUID],
) -> None:
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("validation")
    for case_id in case_ids:
        case = await repo.get_test_case(
            session,
            organization_id=ctx.organization.id,
            test_case_id=case_id,
        )
        if case is None or case.project_id != project_id:
            raise ValueError("validation")


async def create_test_plan_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    body: TestPlanCreateInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project_role(session, ctx, project_id=body.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_CREATE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    name = body.name.strip()
    if not name:
        raise ValueError("validation")

    now = datetime.now(UTC)
    plan_id = uuid.uuid4()
    row = TestPlan(
        id=plan_id,
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        created_by=ctx.user.id,
        aggregate_version=1,
        project_id=body.project_id,
        name=name,
        jira_fix_version=body.jira_fix_version,
        schedule_binding=None,
    )
    await repo.insert_test_plan(session, row)
    response = {"data": serialize_plan_write(row, case_ids=[])}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_CREATE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_plan.create",
            resource_type="test_plan",
            resource_id=plan_id,
            project_id=body.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def patch_test_plan_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_plan_id: uuid.UUID,
    body: TestPlanPatchInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_plan(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PATCH,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.aggregate_version != body.expected_version:
        raise ValueError("version")

    now = datetime.now(UTC)
    if body.name is not None:
        next_name = body.name.strip()
        if not next_name:
            raise ValueError("validation")
        row.name = next_name
    if body.jira_fix_version is not None:
        row.jira_fix_version = body.jira_fix_version
    row.aggregate_version += 1
    row.updated_at = now
    case_ids = await repo.list_plan_case_ids(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
    )
    response = {"data": serialize_plan_write(row, case_ids=case_ids)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PATCH,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_plan.patch",
            resource_type="test_plan",
            resource_id=test_plan_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def put_test_plan_case_ids_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_plan_id: uuid.UUID,
    body: TestPlanCaseIdsInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_plan(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PUT_CASE_IDS,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.aggregate_version != body.expected_version:
        raise ValueError("version")

    await _validate_case_ids_for_plan(
        session,
        ctx,
        project_id=row.project_id,
        case_ids=body.case_ids,
    )

    now = datetime.now(UTC)
    await repo.replace_plan_cases(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
        case_ids=body.case_ids,
        created_by=ctx.user.id,
        created_at=now,
    )
    row.aggregate_version += 1
    row.updated_at = now
    response = {"data": serialize_plan_write(row, case_ids=body.case_ids)}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PUT_CASE_IDS,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_plan.put_case_ids",
            resource_type="test_plan",
            resource_id=test_plan_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


async def put_test_plan_schedule_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_plan_id: uuid.UUID,
    body: TestPlanScheduleInput,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    row = await repo.get_test_plan(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
        for_update=True,
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=WRITE_ROLES)
    existing = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PUT_SCHEDULE,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing.response_ref or {})

    if row.aggregate_version != body.expected_version:
        raise ValueError("version")

    if body.env_id is not None:
        env = await execution_query.get_environment_for_run(
            session,
            organization_id=ctx.organization.id,
            environment_id=body.env_id,
        )
        if env is None:
            raise ValueError("not_found")

    now = datetime.now(UTC)
    binding: dict[str, Any] = dict(row.schedule_binding or {})
    if body.enabled is not None:
        binding["enabled"] = body.enabled
    if body.schedule is not None:
        binding["schedule"] = body.schedule
    if body.env_id is not None:
        binding["env_id"] = str(body.env_id)
    row.schedule_binding = binding
    row.aggregate_version += 1
    row.updated_at = now
    case_ids = await repo.list_plan_case_ids(
        session,
        organization_id=ctx.organization.id,
        test_plan_id=test_plan_id,
    )
    write_payload = serialize_plan_write(row, case_ids=case_ids)
    schedule = _serialize_schedule_binding(binding)
    if schedule is not None and "enabled" in binding:
        write_payload["enabled"] = binding["enabled"]
    if schedule is not None:
        write_payload["schedule"] = schedule.get("schedule")
        if "env_id" in schedule:
            write_payload["env_id"] = schedule["env_id"]
    response = {"data": write_payload}
    await repo.create_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type=COMMAND_PLAN_PUT_SCHEDULE,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="test_plan.put_schedule",
            resource_type="test_plan",
            resource_id=test_plan_id,
            project_id=row.project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    return response


def serialize_version_list_item(
    version: TestCaseVersion,
    *,
    is_current: bool,
) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "created_at": _iso(version.created_at),
        "created_by": str(version.created_by) if version.created_by else None,
        "test_case_id": str(version.test_case_id),
        "version_seq": version.version_seq,
        "data_classification": version.data_classification,
        "is_current": is_current,
    }


def _minimize_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return dict(snapshot)


async def list_test_case_versions_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    cursor: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session, organization_id=ctx.organization.id, test_case_id=test_case_id
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    page_limit = min(limit or 50, 100)
    cursor_version_seq: int | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_version_seq, cursor_id = repo.decode_version_seq_cursor(cursor)
    rows = await repo.list_test_case_versions(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        cursor_version_seq=cursor_version_seq,
        cursor_id=cursor_id,
        limit=page_limit,
    )
    has_more = len(rows) > page_limit
    items = rows[:page_limit]
    next_cursor = None
    if has_more and items:
        last = items[-1]
        next_cursor = repo.encode_version_seq_cursor(
            version_seq=last.version_seq,
            item_id=last.id,
        )
    current_version_id = row.current_version_id
    return {
        "items": [
            serialize_version_list_item(
                item,
                is_current=current_version_id is not None and item.id == current_version_id,
            )
            for item in items
        ],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_test_case_version_snapshot_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    test_case_id: uuid.UUID,
    version_id: uuid.UUID,
) -> dict[str, Any]:
    row = await repo.get_test_case(
        session, organization_id=ctx.organization.id, test_case_id=test_case_id
    )
    if row is None:
        raise ValueError("not_found")
    await _require_project_role(session, ctx, project_id=row.project_id, allowed=READ_ROLES)
    version = await repo.get_test_case_version_for_case(
        session,
        organization_id=ctx.organization.id,
        test_case_id=test_case_id,
        version_id=version_id,
    )
    if version is None:
        raise ValueError("not_found")
    payload = serialize_version_list_item(
        version,
        is_current=row.current_version_id is not None and row.current_version_id == version.id,
    )
    snapshot = _minimize_snapshot(version.snapshot)
    locator_health = snapshot.get("locator_health", [])
    if isinstance(locator_health, list) and not locator_health:
        steps = snapshot.get("steps", [])
        if isinstance(steps, list) and row.case_type == "web":
            derived = extract_locator_health_from_steps(steps)
            snapshot = {**snapshot, "locator_health": derived}
    payload["snapshot"] = snapshot
    return payload
