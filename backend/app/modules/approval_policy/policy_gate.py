"""Pure Policy Gate evaluation (AC-073)."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

DenyReason = Literal["undeclared", "deny", "state"]


class PolicyGate(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_REAUTH = "REQUIRE_REAUTH"


FROZEN_ACTION_LEVELS: dict[str, str | None] = {
    "jira_write": "L2",
    "env_register": "L3",
    "heal_apply": "L3",
    "perf_high_risk": "L3",
    "gate_waiver": "L3",
    "kill_switch_restore": "L3",
    "release_push": "L4",
    "agent_tool_action": None,
    "copilot_write": "DISABLED",
}

PROJECT_SCOPED_ACTIONS = frozenset(
    {
        "jira_write",
        "heal_apply",
        "perf_high_risk",
        "release_push",
        "env_register",
        "agent_tool_action",
        "gate_waiver",
    }
)

ORG_SCOPED_ACTIONS = frozenset({"kill_switch_restore"})

VALID_SIDE_EFFECT_LEVELS = frozenset({"L0", "L1", "L2", "L3", "L4"})


@dataclass(frozen=True)
class GateEvaluation:
    gate: PolicyGate
    side_effect_level: str | None = None
    deny_reason: DenyReason | None = None


def resolve_side_effect_level(action_type: str, payload: dict[str, Any]) -> str | None:
    if action_type not in FROZEN_ACTION_LEVELS:
        return None
    frozen = FROZEN_ACTION_LEVELS[action_type]
    if frozen == "DISABLED":
        return None
    if frozen is not None:
        return frozen
    declared = payload.get("declared_side_effect_level")
    if not isinstance(declared, str) or declared not in VALID_SIDE_EFFECT_LEVELS:
        return None
    return declared


def evaluate_policy_gate(
    *,
    action_type: str,
    payload: dict[str, Any],
    reauth_required: bool,
) -> GateEvaluation:
    if action_type not in FROZEN_ACTION_LEVELS:
        return GateEvaluation(gate=PolicyGate.DENY, deny_reason="undeclared")

    if action_type == "copilot_write":
        return GateEvaluation(gate=PolicyGate.DENY, deny_reason="state")

    level = resolve_side_effect_level(action_type, payload)
    if level is None:
        return GateEvaluation(gate=PolicyGate.DENY, deny_reason="undeclared")

    if action_type == "perf_high_risk":
        return GateEvaluation(
            gate=PolicyGate.DENY,
            side_effect_level=level,
            deny_reason="undeclared",
        )

    if level in {"L0", "L1"}:
        return GateEvaluation(gate=PolicyGate.ALLOW, side_effect_level=level)

    if level == "L2":
        return GateEvaluation(gate=PolicyGate.REQUIRE_APPROVAL, side_effect_level=level)

    if level in {"L3", "L4"}:
        if reauth_required:
            return GateEvaluation(
                gate=PolicyGate.REQUIRE_REAUTH,
                side_effect_level=level,
            )
        return GateEvaluation(gate=PolicyGate.REQUIRE_APPROVAL, side_effect_level=level)

    return GateEvaluation(gate=PolicyGate.DENY, side_effect_level=level, deny_reason="undeclared")
