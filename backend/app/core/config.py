import ipaddress
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

PRODUCTION_ENV = "production"

# Hosts that can only ever address the local machine, including the mock IdP.
_LOCAL_ISSUER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def loopback_issuer_host(issuer: str) -> str | None:
    """Return the host when ``issuer`` addresses the local machine, else None."""
    host = urlparse(issuer).hostname
    if host is None:
        return None
    normalized = host.strip("[]").lower()
    if normalized in _LOCAL_ISSUER_HOSTS:
        return host
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return host
    except ValueError:
        return None
    return None


class SameSitePolicy(StrEnum):
    LAX = "Lax"
    STRICT = "Strict"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str
    app_port: int
    log_level: str
    database_url: str

    session_cookie_name: str
    session_cookie_samesite: SameSitePolicy
    session_cookie_secure: bool
    session_ttl_seconds: int
    oidc_login_draft_ttl_seconds: int
    reauth_window_seconds: int
    approval_ttl_seconds: int

    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    oidc_claim_subject: str

    github_webhook_secret: str
    jenkins_webhook_secret: str | None = None
    jenkins_api_token: str | None = None

    test_run_heartbeat_timeout_seconds: int | None = None
    artifact_root: str
    ci_log_chunk_bytes: int | None = None
    ci_log_max_total_bytes: int | None = None
    report_parse_timeout_seconds: int | None = None
    report_parse_batch_rows: int | None = None

    @field_validator("test_run_heartbeat_timeout_seconds", mode="before")
    @classmethod
    def validate_heartbeat_timeout(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "ci_log_chunk_bytes",
        "ci_log_max_total_bytes",
        "report_parse_timeout_seconds",
        "report_parse_batch_rows",
        mode="before",
    )
    @classmethod
    def validate_optional_int(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("session_cookie_samesite", mode="before")
    @classmethod
    def validate_samesite(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.lower() == "lax":
                return SameSitePolicy.LAX
            if normalized.lower() == "strict":
                return SameSitePolicy.STRICT
        return value

    @field_validator("session_cookie_secure", mode="before")
    @classmethod
    def validate_secure(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
        return value

    @model_validator(mode="after")
    def reject_local_mock_idp_in_production(self) -> Self:
        """Refuse to boot a production process pointed at the local mock IdP."""
        if self.app_env.strip().lower() != PRODUCTION_ENV:
            return self
        if loopback_issuer_host(self.oidc_issuer) is not None:
            raise ValueError(
                f"OIDC_ISSUER must not address the local mock IdP when APP_ENV={PRODUCTION_ENV}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
