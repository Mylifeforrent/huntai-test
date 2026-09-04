from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
