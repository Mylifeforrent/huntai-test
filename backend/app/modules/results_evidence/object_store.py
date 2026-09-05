"""Local volume storage for Playwright artifacts (M0/M1)."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from app.core.config import get_settings

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _artifact_root() -> Path:
    root = Path(get_settings().artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_filename(name: str) -> str:
    cleaned = _SAFE_FILENAME.sub("_", name.strip())
    return cleaned or "artifact.bin"


def generate_object_key(
    *,
    organization_id: uuid.UUID,
    artifact_id: uuid.UUID,
    filename: str,
) -> str:
    safe = sanitize_filename(filename)
    return f"{organization_id}/{artifact_id}/{safe}"


def resolve_path(object_key: str) -> Path:
    root = _artifact_root().resolve()
    candidate = (root / object_key).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("invalid_object_key") from exc
    return candidate


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_bytes(*, object_key: str, data: bytes) -> str:
    path = resolve_path(object_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_hex(data)


def read_bytes(object_key: str) -> bytes:
    path = resolve_path(object_key)
    if not path.is_file():
        raise FileNotFoundError(object_key)
    return path.read_bytes()


def file_exists(object_key: str) -> bool:
    try:
        return resolve_path(object_key).is_file()
    except ValueError:
        return False


def verify_checksum(object_key: str, expected_checksum: str) -> bool:
    if not file_exists(object_key):
        return False
    actual = sha256_hex(read_bytes(object_key))
    return actual == expected_checksum
