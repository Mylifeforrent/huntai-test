"""Parse OpenAPI / Postman / curl import sources into endpoint descriptors."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


@dataclass(frozen=True)
class ParsedEndpoint:
    method: str
    path: str
    name: str


@dataclass(frozen=True)
class ParseResult:
    endpoints: list[ParsedEndpoint]
    failed_items: list[dict[str, str]]


def _endpoint_name(method: str, path: str, operation: dict[str, Any] | None = None) -> str:
    if operation:
        op_id = operation.get("operationId")
        if isinstance(op_id, str) and op_id.strip():
            return op_id.strip()
        summary = operation.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return f"{method.upper()} {path}"


def parse_openapi_content(content: str) -> ParseResult:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("file_validation") from exc
    if not isinstance(data, dict):
        raise ValueError("file_validation")
    if content.lstrip().startswith("---") or (
        "openapi" not in data and "swagger" not in data and "paths" not in data
    ):
        # YAML heuristic without PyYAML
        stripped = content.lstrip()
        if stripped.startswith("openapi:") or stripped.startswith("swagger:"):
            raise ValueError("file_validation")
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("file_validation")
    endpoints: list[ParsedEndpoint] = []
    failed_items: list[dict[str, str]] = []
    for path_key, path_item in paths.items():
        if not isinstance(path_item, dict):
            failed_items.append(
                {"endpoint": str(path_key), "reason": "Path item must be an object"}
            )
            continue
        for method, operation in path_item.items():
            method_lower = str(method).lower()
            if method_lower not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                failed_items.append(
                    {
                        "endpoint": f"{method_lower.upper()} {path_key}",
                        "reason": "Operation must be an object",
                    }
                )
                continue
            endpoints.append(
                ParsedEndpoint(
                    method=method_lower.upper(),
                    path=str(path_key),
                    name=_endpoint_name(method_lower.upper(), str(path_key), operation),
                )
            )
    return ParseResult(endpoints=endpoints, failed_items=failed_items)


def _parse_postman_url(url_value: Any) -> str:
    if isinstance(url_value, str):
        return url_value
    if isinstance(url_value, dict):
        raw = url_value.get("raw")
        if isinstance(raw, str):
            return raw
        host = url_value.get("host")
        path_parts = url_value.get("path")
        if isinstance(host, list) and isinstance(path_parts, list):
            host_part = ".".join(str(p) for p in host)
            path_part = "/".join(str(p) for p in path_parts)
            return f"https://{host_part}/{path_part}"
    return ""


def _walk_postman_items(items: list[Any], endpoints: list[ParsedEndpoint]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("item")
        if isinstance(nested, list):
            _walk_postman_items(nested, endpoints)
            continue
        request = item.get("request")
        if not isinstance(request, dict):
            continue
        method = str(request.get("method", "GET")).upper()
        url = _parse_postman_url(request.get("url"))
        name = str(item.get("name") or f"{method} {url}")
        path = url
        if "://" in url:
            path = "/" + url.split("://", 1)[1].split("/", 1)[-1]
        endpoints.append(ParsedEndpoint(method=method, path=path or "/", name=name))


def parse_postman_content(content: str) -> ParseResult:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("file_validation") from exc
    if not isinstance(data, dict):
        raise ValueError("file_validation")
    items = data.get("item")
    if not isinstance(items, list):
        raise ValueError("file_validation")
    endpoints: list[ParsedEndpoint] = []
    _walk_postman_items(items, endpoints)
    return ParseResult(endpoints=endpoints, failed_items=[])


_CURL_METHOD_RE = re.compile(r"-X\s+(\w+)", re.IGNORECASE)
_CURL_URL_RE = re.compile(r"curl\s+(?:[^\s]+\s+)*['\"]?(https?://[^\s'\"]+)")


def parse_curl_content(content: str) -> ParseResult:
    line = content.strip().splitlines()[0] if content.strip() else ""
    method = "GET"
    match_method = _CURL_METHOD_RE.search(line)
    if match_method:
        method = match_method.group(1).upper()
    match_url = _CURL_URL_RE.search(line)
    if not match_url:
        raise ValueError("file_validation")
    url = match_url.group(1)
    path = "/" + url.split("://", 1)[1].split("/", 1)[-1] if "://" in url else url
    return ParseResult(
        endpoints=[ParsedEndpoint(method=method, path=path, name=f"{method} {path}")],
        failed_items=[],
    )


def parse_source_content(source_type: str, content: str) -> ParseResult:
    if source_type == "openapi":
        return parse_openapi_content(content)
    if source_type == "postman":
        return parse_postman_content(content)
    if source_type == "curl":
        return parse_curl_content(content)
    raise ValueError("validation")


def build_draft_case(endpoint: ParsedEndpoint) -> dict[str, Any]:
    return {
        "name": endpoint.name,
        "priority": "P2",
        "case_type": "api",
        "steps": [
            {
                "action": "request",
                "params": {"method": endpoint.method, "path": endpoint.path},
            }
        ],
        "assertions": [
            {"type": "status_code", "expression": "$.status", "expected": 200},
            {"type": "json_path", "expression": "$.id", "expected": None},
        ],
        "tags": ["ai-generated"],
    }
