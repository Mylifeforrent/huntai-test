"""Domain checks for project member last-owner invariant."""

from app.modules.identity_tenancy.service import is_last_owner_violation


def test_last_owner_demote_is_violation() -> None:
    assert is_last_owner_violation(current_role="owner", target_role="admin", owner_count=1) is True


def test_last_owner_remove_is_violation() -> None:
    assert is_last_owner_violation(current_role="owner", target_role=None, owner_count=1) is True


def test_non_last_owner_demote_ok() -> None:
    assert (
        is_last_owner_violation(current_role="owner", target_role="tester", owner_count=2) is False
    )


def test_admin_demote_never_last_owner_violation() -> None:
    assert (
        is_last_owner_violation(current_role="admin", target_role="viewer", owner_count=1) is False
    )


def test_owner_stays_owner_ok() -> None:
    assert (
        is_last_owner_violation(current_role="owner", target_role="owner", owner_count=1) is False
    )
