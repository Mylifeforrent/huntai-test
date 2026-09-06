"""Copilot minimal services (API-190…193, FR-16, S-M3-04).

Read-only assistant: server-side sessions, whitelisted read-only tool
(`query_test_assets`) anchored to the session's project, citation validation
against caller RBAC, full AIInvocationLog via the LLM factory, kill switch and
token budget enforced before any model call (AC-068/069).
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeInput, invoke
from app.modules.ai_governance.models import CopilotSession
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.quota_governance import query_port as quota_query
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

READ_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "tester"})
WHITELISTED_TOOLS = frozenset({"query_test_assets"})
KILL_SWITCH_MODULE = "copilot"
KILL_SWITCH_CAPABILITY = "A6"
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
MESSAGE_CONTENT_MAX = 4000
MESSAGE_STORED_MAX = 400


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def serialize_session(row: CopilotSession, *, include_messages: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "title": row.title,
        "updated_at": _iso(row.updated_at),
        "data_classification": row.data_classification,
        "selected_skill_version_id": (
            str(row.selected_skill_version_id) if row.selected_skill_version_id else None
        ),
        "project_id": str(row.project_id) if row.project_id else None,
    }
    if include_messages:
        payload["messages"] = [
            {
                "role": message.get("role"),
                "content": str(message.get("content", ""))[:MESSAGE_STORED_MAX],
                **(
                    {"args_hash": message["args_hash"]}
                    if isinstance(message.get("args_hash"), str)
                    else {}
                ),
            }
            for message in (row.messages or [])
            if isinstance(message, dict)
        ]
    return payload


async def _require_session_owner(
    session: AsyncSession, ctx: SessionContext, row: CopilotSession
) -> None:
    if row.user_id != ctx.user.id:
        raise ValueError("not_found")


async def create_session_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    title: str | None,
    project_id: uuid.UUID | None,
    selected_skill_version_id: uuid.UUID | None,
) -> dict[str, Any]:
    role = await identity_query.caller_is_org_member(
        session, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if role is None or role not in WRITE_ROLES:
        raise ValueError("forbidden")
    if selected_skill_version_id is not None:
        # Skill/SkillVersion domain is M4; unversioned skills never reach prod.
        raise ValueError("not_found")
    if project_id is not None and not await identity_query.project_exists_in_org(
        session, organization_id=ctx.organization.id, project_id=project_id
    ):
        raise ValueError("not_found")
    now = _now()
    row = CopilotSession(
        id=uuid.uuid4(),
        organization_id=ctx.organization.id,
        created_at=now,
        updated_at=now,
        aggregate_version=1,
        user_id=ctx.user.id,
        project_id=project_id,
        title=title,
        selected_skill_version_id=None,
        messages=[],
        data_classification="Confidential",
    )
    session.add(row)
    await session.flush()
    return serialize_session(row)


async def list_sessions_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    limit: int | None,
) -> dict[str, Any]:
    page_limit = min(limit or 50, 200)
    result = await session.execute(
        select(CopilotSession)
        .where(
            CopilotSession.organization_id == ctx.organization.id,
            CopilotSession.user_id == ctx.user.id,
        )
        .order_by(CopilotSession.updated_at.desc(), CopilotSession.id.desc())
        .limit(page_limit + 1)
    )
    rows = list(result.scalars().all())
    has_more = len(rows) > page_limit
    rows = rows[:page_limit]
    return {
        "items": [serialize_session(row) for row in rows],
        "page": {"has_more": has_more, "next_cursor": None},
    }


async def get_session_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    session_id: uuid.UUID,
) -> dict[str, Any]:
    row = await _get_owned_session(session, ctx, session_id=session_id)
    return serialize_session(row, include_messages=True)


async def _get_owned_session(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    session_id: uuid.UUID,
    for_update: bool = False,
) -> CopilotSession:
    query = select(CopilotSession).where(
        CopilotSession.organization_id == ctx.organization.id,
        CopilotSession.id == session_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError("not_found")
    await _require_session_owner(session, ctx, row)
    return row


async def _kill_switch_active(session: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    controls = await identity_query.get_capability_controls(
        session, organization_id=organization_id
    )
    modules = controls.get("tightened_modules") if isinstance(controls, dict) else []
    capabilities = controls.get("tightened_capabilities") if isinstance(controls, dict) else []
    module_names = {str(item) for item in modules} if isinstance(modules, list) else set()
    capability_names = (
        {str(item) for item in capabilities} if isinstance(capabilities, list) else set()
    )
    return KILL_SWITCH_MODULE in module_names or KILL_SWITCH_CAPABILITY in capability_names


def _requested_tool(content: str) -> str | None:
    lowered = content.lower()
    if "query_test_assets" in lowered:
        return "query_test_assets"
    return None


def _extract_foreign_uuids(content: str) -> list[str]:
    return [item.lower() for item in UUID_PATTERN.findall(content)]


async def _uuid_in_scope(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    candidate: uuid.UUID,
) -> bool:
    from app.modules.run_orchestration import repository as run_repo
    from app.modules.test_assets import repository as test_assets_repo

    run = await run_repo.get_test_run(
        session, organization_id=organization_id, test_run_id=candidate
    )
    if run is not None:
        return run.project_id == project_id
    case = await test_assets_repo.get_test_case(
        session, organization_id=organization_id, test_case_id=candidate
    )
    return case is not None


async def post_message_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    session_id: uuid.UUID,
    content: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    _ = idempotency_key  # 建议 header；管线幂等由 AIInvocationLog 承担
    row = await _get_owned_session(session, ctx, session_id=session_id, for_update=True)
    if await _kill_switch_active(session, organization_id=ctx.organization.id):
        # AC-069: the command itself fails — not a display-only switch.
        raise ValueError("policy_kill")
    if await quota_query.token_budget_exhausted(session, organization_id=ctx.organization.id):
        raise ValueError("quota")

    refused_policies: list[str] = []
    foreign_ids = _extract_foreign_uuids(content)
    anchored_project = row.project_id
    if anchored_project is not None:
        for raw_id in foreign_ids:
            candidate = uuid.UUID(raw_id)
            if not await _uuid_in_scope(
                session,
                organization_id=ctx.organization.id,
                project_id=anchored_project,
                candidate=candidate,
            ):
                # AC-068: cross-project/cross-tenant references never yield data.
                refused_policies.append(f"cross_project_reference:{raw_id}")
    requested_tool = _requested_tool(content)
    if requested_tool is not None and requested_tool not in WHITELISTED_TOOLS:
        refused_policies.append(f"tool_not_allowlisted:{requested_tool}")

    tool_calls: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    answer: str
    if anchored_project is None:
        answer = "会话未绑定项目上下文，无法查询测试资产。请创建绑定项目的会话。"
        refused_policies.append("no_project_anchor")
    else:
        runs_summary = await _query_test_assets(
            session,
            organization_id=ctx.organization.id,
            project_id=anchored_project,
        )
        args_hash = hashlib.sha256(
            json.dumps({"project_id": str(anchored_project)}, sort_keys=True).encode()
        ).hexdigest()
        tool_calls.append(
            {
                "tool": "query_test_assets",
                "args_hash": args_hash,
                "result_summary": runs_summary["summary"],
            }
        )
        citations = runs_summary["citations"]
        answer = runs_summary["answer"]
        for raw_id in foreign_ids:
            if raw_id not in {citation["resource_id"] for citation in citations}:
                answer += f"（引用 {raw_id} 不在可访问范围内，已拒绝。）"

    output = await invoke(
        session,
        InvokeInput(
            organization_id=ctx.organization.id,
            user_id=ctx.user.id,
            task_type="general",
            prompt_version="copilot-a6@1.0.0",
            capability_id="A6",
            module="ai_governance",
            copilot_session_id=row.id,
            data_classification="Confidential",
        ),
    )
    if output.result != "ok":
        refused_policies.append(f"llm_result:{output.result}")
        answer = f"{answer}（AI 生成降级，以上为服务端只读查询结果。）"

    a6: dict[str, Any] = {
        "answer": answer,
        "citations": citations,
        "tool_calls": tool_calls,
        "refused_policies": refused_policies,
        "meta": {
            "ai_invocation_log_id": str(output.log_id),
            "copilot_session_id": str(row.id),
        },
    }
    messages = list(row.messages or [])
    messages.append({"role": "user", "content": content[:MESSAGE_CONTENT_MAX]})
    messages.append(
        {
            "role": "assistant",
            "content": answer[:MESSAGE_CONTENT_MAX],
            "args_hash": tool_calls[0]["args_hash"] if tool_calls else None,
        }
    )
    row.messages = messages
    row.updated_at = _now()
    row.aggregate_version += 1
    await session.flush()
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="copilot.message",
            resource_type="copilot_session",
            resource_id=row.id,
            result="ok",
        ),
    )
    return {
        "answer": a6["answer"],
        "citations": a6["citations"],
        "tool_calls": a6["tool_calls"],
        "refused_policies": a6["refused_policies"],
        "meta": a6["meta"],
    }


async def _query_test_assets(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any]:
    """Whitelisted read-only tool, anchored to the session project (RBAC)."""
    from app.modules.results_evidence import query_port as evidence_query
    from app.modules.run_orchestration import query_port as run_query

    run_ids = await run_query.list_run_ids_for_project(
        session, organization_id=organization_id, project_id=project_id
    )
    citations = [
        {"source_type": "platform", "resource_id": str(run_id), "evidence_ref": None}
        for run_id in run_ids[:5]
    ]
    summary = f"项目最近 TestRun {len(run_ids)} 个"
    _ = evidence_query
    return {
        "answer": f"{summary}。以上为服务端只读查询结果（引用均在可访问范围内）。",
        "summary": summary,
        "citations": citations,
    }
