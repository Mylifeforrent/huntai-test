"""A2 failure triage — invoke, parse, rule fallback."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_governance.llm_factory import InvokeInput, invoke

PROMPT_VERSION = "prompt/failure-triage@1.0.0"

VALID_CATEGORIES = frozenset(
    {
        "env_down",
        "auth_expired",
        "locator_stale",
        "assertion_real_bug",
        "flaky",
        "data_issue",
        "unknown",
    }
)
VALID_BLOCKING = frozenset({"blocker", "non_blocker", "uncertain"})
ASSERTION_TYPES_FOR_BUG = frozenset({"status_code", "equals", "contains", "json_path", "header"})


@dataclass(frozen=True)
class ClusterDraft:
    category: str
    root_cause: str | None
    confidence: float
    blocking_judgment: str
    evidence_refs: list[uuid.UUID]
    failure_refs: list[uuid.UUID]
    fixes: list[dict[str, Any]]


@dataclass(frozen=True)
class TriageResult:
    clusters: list[ClusterDraft]
    unclustered_refs: list[uuid.UUID]
    degraded: bool
    generation_status: str


def _extract_structured_output(usage: dict[str, Any]) -> dict[str, Any] | None:
    raw = usage.get("structured_output")
    if isinstance(raw, dict):
        return raw
    return None


def _parse_fixes(raw_fixes: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_fixes, list):
        return []
    fixes: list[dict[str, Any]] = []
    for item in raw_fixes:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        if not isinstance(field, str) or not field.strip():
            continue
        confidence_raw = item.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw)
        except TypeError, ValueError:
            confidence = 0.0
        fixes.append(
            {
                "field": field,
                "current": str(item.get("current", "")),
                "suggested": str(item.get("suggested", "")),
                "reason": str(item.get("reason", "")),
                "confidence": confidence,
                "can_auto_apply": False,
            }
        )
    return fixes


def _validate_ai_clusters(
    payload: dict[str, Any],
    *,
    evidence_pool: set[uuid.UUID],
    failed_case_ids: set[uuid.UUID],
) -> tuple[list[ClusterDraft], list[uuid.UUID]] | None:
    clusters_raw = payload.get("clusters")
    if not isinstance(clusters_raw, list):
        return None
    unclustered_raw = payload.get("unclustered_refs", [])
    unclustered: list[uuid.UUID] = []
    if isinstance(unclustered_raw, list):
        for item in unclustered_raw:
            try:
                unclustered.append(uuid.UUID(str(item)))
            except ValueError:
                return None

    drafts: list[ClusterDraft] = []
    for cluster in clusters_raw:
        if not isinstance(cluster, dict):
            return None
        category = str(cluster.get("category", ""))
        if category not in VALID_CATEGORIES:
            return None
        blocking = str(cluster.get("blocking_judgment", ""))
        if blocking not in VALID_BLOCKING:
            return None
        try:
            confidence = float(cluster.get("confidence", -1))
        except TypeError, ValueError:
            return None
        if confidence < 0.0 or confidence > 1.0:
            return None
        failure_refs: list[uuid.UUID] = []
        for ref in cluster.get("failure_refs", []):
            try:
                case_result_id = uuid.UUID(str(ref))
            except ValueError:
                return None
            if case_result_id not in failed_case_ids:
                return None
            failure_refs.append(case_result_id)
        evidence_refs: list[uuid.UUID] = []
        for ref in cluster.get("evidence_refs", []):
            try:
                evidence_id = uuid.UUID(str(ref))
            except ValueError:
                return None
            evidence_refs.append(evidence_id)
        if evidence_refs:
            if not evidence_pool:
                return None
            if any(ref not in evidence_pool for ref in evidence_refs):
                return None
        root_cause = cluster.get("root_cause")
        root_text = str(root_cause) if root_cause is not None else None
        fixes = _parse_fixes(cluster.get("fixes"))
        if not fixes:
            fixes = _parse_fixes(cluster.get("suggested_actions"))
        drafts.append(
            ClusterDraft(
                category=category,
                root_cause=root_text,
                confidence=confidence,
                blocking_judgment=blocking,
                evidence_refs=evidence_refs,
                failure_refs=failure_refs,
                fixes=fixes,
            )
        )
    return drafts, unclustered


def _status_class(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    if status_code in {401, 403}:
        return "auth"
    if status_code >= 500:
        return "5xx"
    return "other"


def _rule_category_for_case(case: dict[str, Any]) -> str:
    summary = case.get("normalized_summary")
    if isinstance(summary, dict):
        status_code = summary.get("status_code")
        if isinstance(status_code, int):
            if status_code in {401, 403}:
                return "auth_expired"
            if status_code >= 500:
                return "env_down"
    steps = case.get("step_assertions", [])
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            assertions = step.get("assertion_results")
            items: list[Any] = []
            if isinstance(assertions, dict):
                raw_items = assertions.get("items")
                if isinstance(raw_items, list):
                    items = raw_items
            elif isinstance(assertions, list):
                items = assertions
            for assertion in items:
                if not isinstance(assertion, dict):
                    continue
                atype = str(assertion.get("type", ""))
                passed = assertion.get("passed")
                if atype in ASSERTION_TYPES_FOR_BUG and passed is False:
                    return "assertion_real_bug"
            observation_ref = step.get("observation_ref")
            if observation_ref is None and step.get("is_incomplete"):
                return "env_down"
    if isinstance(summary, dict):
        error = str(summary.get("error", "")).lower()
        if any(token in error for token in ("connection", "timeout", "refused", "unreachable")):
            return "env_down"
    return "unknown"


def _group_key(case: dict[str, Any]) -> tuple[str, str | None, str | None]:
    summary = case.get("normalized_summary")
    status_code: int | None = None
    path: str | None = None
    if isinstance(summary, dict):
        raw_status = summary.get("status_code")
        if isinstance(raw_status, int):
            status_code = raw_status
        raw_path = summary.get("path")
        if isinstance(raw_path, str):
            path = raw_path
    category = _rule_category_for_case(case)
    status_class = _status_class(status_code)
    third = path if category in {"env_down", "assertion_real_bug"} else None
    return category, status_class, third


def rule_cluster_failed_cases(
    failed_cases: list[dict[str, Any]],
) -> TriageResult:
    groups: dict[tuple[str, str | None, str | None], list[uuid.UUID]] = {}
    case_by_id: dict[uuid.UUID, dict[str, Any]] = {}
    for case in failed_cases:
        case_id = uuid.UUID(str(case["id"]))
        case_by_id[case_id] = case
        key = _group_key(case)
        groups.setdefault(key, []).append(case_id)

    clusters: list[ClusterDraft] = []
    clustered: set[uuid.UUID] = set()
    for key, refs in groups.items():
        category = key[0]
        clustered.update(refs)
        clusters.append(
            ClusterDraft(
                category=category,
                root_cause="Rule-based clustering fallback",
                confidence=0.3,
                blocking_judgment="uncertain",
                evidence_refs=[],
                failure_refs=refs,
                fixes=[],
            )
        )
    unclustered = [case_id for case_id in case_by_id if case_id not in clustered]
    return TriageResult(
        clusters=clusters,
        unclustered_refs=unclustered,
        degraded=True,
        generation_status="degraded",
    )


async def run_a2_triage(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID | None,
    failed_cases: list[dict[str, Any]],
    evidence_pool: set[uuid.UUID],
) -> TriageResult:
    failed_case_ids = {uuid.UUID(str(item["id"])) for item in failed_cases}
    if not failed_case_ids:
        return TriageResult(
            clusters=[],
            unclustered_refs=[],
            degraded=False,
            generation_status="ready",
        )

    async def _try_invoke() -> tuple[list[ClusterDraft], list[uuid.UUID]] | None:
        output = await invoke(
            session,
            InvokeInput(
                organization_id=organization_id,
                user_id=user_id or organization_id,
                task_type="general",
                prompt_version=PROMPT_VERSION,
                capability_id="A2",
                module="results_evidence",
                data_classification="Confidential",
            ),
        )
        if output.result != "ok":
            return None
        structured = _extract_structured_output(output.usage)
        if structured is None:
            return None
        return _validate_ai_clusters(
            structured,
            evidence_pool=evidence_pool,
            failed_case_ids=failed_case_ids,
        )

    parsed = await _try_invoke()
    if parsed is None:
        parsed = await _try_invoke()
    if parsed is not None:
        drafts, unclustered = parsed
        return TriageResult(
            clusters=drafts,
            unclustered_refs=unclustered,
            degraded=False,
            generation_status="ready",
        )
    return rule_cluster_failed_cases(failed_cases)


def confidence_to_decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))
