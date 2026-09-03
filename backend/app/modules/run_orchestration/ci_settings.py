"""Resolve Jenkins env refs without importing integration_hub."""

from __future__ import annotations

from app.core.config import Settings

ALLOWED_JENKINS_ENV_REF_KEYS = frozenset({"JENKINS_API_TOKEN", "JENKINS_WEBHOOK_SECRET"})


def resolve_jenkins_env_ref(settings: Settings, ref: str | None) -> str | None:
    if ref is None:
        return None
    stripped = ref.strip()
    if not stripped.startswith("env:"):
        return None
    key = stripped[4:]
    if key not in ALLOWED_JENKINS_ENV_REF_KEYS:
        return None
    if key == "JENKINS_API_TOKEN":
        return settings.jenkins_api_token or None
    if key == "JENKINS_WEBHOOK_SECRET":
        return settings.jenkins_webhook_secret or None
    return None
