"""Minimal recursive subset validator for Job Schema (M1 external_ci)."""

from __future__ import annotations

from typing import Any

_ALLOWED_TYPES = frozenset({"string", "number", "integer", "boolean"})


def validate_params_against_schema(
    params: dict[str, Any],
    schema: dict[str, Any] | None,
) -> list[str]:
    if schema is None:
        return []
    if schema.get("type") != "object":
        return ["schema_root_must_be_object"]
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        return ["schema_properties_invalid"]
    props: dict[str, Any] = properties if isinstance(properties, dict) else {}
    required_raw = schema.get("required", [])
    required: list[str] = required_raw if isinstance(required_raw, list) else []
    errors: list[str] = []
    for key in required:
        if not isinstance(key, str):
            continue
        if key not in params:
            errors.append(f"missing_required:{key}")
    for key, value in params.items():
        if key not in props:
            continue
        prop_schema = props[key]
        if not isinstance(prop_schema, dict):
            errors.append(f"invalid_property_schema:{key}")
            continue
        type_name = prop_schema.get("type")
        if type_name not in _ALLOWED_TYPES:
            errors.append(f"unsupported_type:{key}")
            continue
        if not _value_matches_type(value, str(type_name)):
            errors.append(f"type_mismatch:{key}")
    return errors


def _value_matches_type(value: Any, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False
