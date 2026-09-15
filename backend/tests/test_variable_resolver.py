from app.modules.run_orchestration.variable_resolver import validate_and_resolve_snapshot


def test_bound_mustache_resolves() -> None:
    steps, assertions, errors = validate_and_resolve_snapshot(
        params={"pet": "dogs", "TARGET_ENV": "https://example.test"},
        steps=[{"action": "request", "params": {"method": "GET", "path": "/{{pet}}"}}],
        assertions=[{"type": "status_code", "expected": 200}],
    )
    assert errors == []
    assert steps[0]["params"]["path"] == "/dogs"


def test_function_placeholder_always_unresolved() -> None:
    _, _, errors = validate_and_resolve_snapshot(
        params={"TARGET_ENV": "https://example.test"},
        steps=[{"action": "request", "params": {"method": "GET", "path": "/${uuid()}"}}],
        assertions=[],
    )
    assert "function_catalog_unavailable: ${uuid()}" in errors
    assert "${uuid()}" not in errors


def test_unbound_mustache_without_function_catalog_prefix() -> None:
    _, _, errors = validate_and_resolve_snapshot(
        params={"TARGET_ENV": "https://example.test"},
        steps=[{"action": "request", "params": {"method": "GET", "path": "/{{missing}}"}}],
        assertions=[],
    )
    assert errors == ["{{missing}}"]
    assert not any(item.startswith("function_catalog_unavailable:") for item in errors)
