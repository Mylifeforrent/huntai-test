"""Table-driven AC-073 Policy Gate unit tests."""

import pytest

from app.modules.approval_policy.policy_gate import (
    PolicyGate,
    evaluate_policy_gate,
    resolve_side_effect_level,
)

ALL_ACTION_TYPES = [
    "jira_write",
    "env_register",
    "heal_apply",
    "perf_high_risk",
    "gate_waiver",
    "kill_switch_restore",
    "agent_tool_action",
    "release_push",
    "copilot_write",
]


@pytest.mark.parametrize("action_type", ALL_ACTION_TYPES)
def test_resolve_side_effect_level_frozen_actions(action_type: str) -> None:
    if action_type == "agent_tool_action":
        assert resolve_side_effect_level(action_type, {}) is None
        assert resolve_side_effect_level(action_type, {"declared_side_effect_level": "L1"}) == "L1"
        return
    if action_type == "copilot_write":
        assert resolve_side_effect_level(action_type, {}) is None
        return
    level = resolve_side_effect_level(action_type, {})
    assert level is not None
    assert level.startswith("L")


@pytest.mark.parametrize(
    ("action_type", "payload", "reauth", "expected_gate", "deny_reason"),
    [
        ("unknown_action", {}, False, PolicyGate.DENY, "undeclared"),
        ("agent_tool_action", {}, False, PolicyGate.DENY, "undeclared"),
        ("copilot_write", {}, False, PolicyGate.DENY, "state"),
        ("jira_write", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("env_register", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("heal_apply", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("gate_waiver", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("kill_switch_restore", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("release_push", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
        ("perf_high_risk", {}, False, PolicyGate.DENY, "undeclared"),
        (
            "agent_tool_action",
            {"declared_side_effect_level": "L0"},
            False,
            PolicyGate.ALLOW,
            None,
        ),
        (
            "agent_tool_action",
            {"declared_side_effect_level": "L1"},
            False,
            PolicyGate.ALLOW,
            None,
        ),
        (
            "agent_tool_action",
            {"declared_side_effect_level": "L2"},
            False,
            PolicyGate.REQUIRE_APPROVAL,
            None,
        ),
        ("env_register", {}, True, PolicyGate.REQUIRE_REAUTH, None),
        ("release_push", {}, True, PolicyGate.REQUIRE_REAUTH, None),
        ("kill_switch_restore", {}, True, PolicyGate.REQUIRE_REAUTH, None),
        ("env_register", {}, False, PolicyGate.REQUIRE_APPROVAL, None),
    ],
)
def test_evaluate_policy_gate_table(
    action_type: str,
    payload: dict[str, object],
    reauth: bool,
    expected_gate: PolicyGate,
    deny_reason: str | None,
) -> None:
    result = evaluate_policy_gate(
        action_type=action_type,
        payload=payload,
        reauth_required=reauth,
    )
    assert result.gate == expected_gate
    assert result.deny_reason == deny_reason
