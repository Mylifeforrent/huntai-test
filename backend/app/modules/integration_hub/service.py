import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.integration_hub import repository as repo
from app.modules.integration_hub.models import (
    ApiToken,
    Connector,
    ExternalObservation,
    ProjectCiTriggerConfig,
)
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

COMMAND_TYPE_BIND_CREDENTIAL = "connector.bind_credential_ref"
COMMAND_TYPE_ISSUE_TOKEN = "api_token.issue"
COMMAND_TYPE_REVOKE_TOKEN = "api_token.revoke"
COMMAND_TYPE_CONNECTOR_REGISTER = "connector.register"
COMMAND_TYPE_CONNECTOR_PATCH = "connector.patch"
COMMAND_TYPE_OUTBOUND_CHANNELS = "connector.put_outbound_channels"
COMMAND_TYPE_CI_TRIGGER_BINDINGS = "project.put_ci_trigger_bindings"
TOKEN_PREFIX_LITERAL = "ht_live_"
TOKEN_PREFIX_DISPLAY_LEN = 16
PASSWORD_HASHER = PasswordHasher()
ALLOWED_ENV_REF_KEYS = frozenset(
    {"GITHUB_WEBHOOK_SECRET", "JENKINS_WEBHOOK_SECRET", "JENKINS_API_TOKEN"}
)
SECRET_PATTERN = re.compile(
    r"(password|secret|token|credential)",
    re.IGNORECASE,
)
OUTBOUND_KIND_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
OUTBOUND_ENV_REF_PATTERN = re.compile(r"^env:[A-Z][A-Z0-9_]*$")
WEBHOOK_SOURCE = "webhook"
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _credential_present(connector: Connector) -> bool:
    return bool(connector.credential_ref and connector.credential_ref.strip())


def _webhook_secret_present(connector: Connector) -> bool:
    return bool(connector.webhook_secret_ref and connector.webhook_secret_ref.strip())


def serialize_list_item(connector: Connector) -> dict[str, Any]:
    has_credential = _credential_present(connector)
    has_webhook_secret = _webhook_secret_present(connector)
    return {
        "id": str(connector.id),
        "type": connector.type,
        "name": connector.name,
        "auth_method": connector.auth_method,
        "has_credential": has_credential,
        "has_webhook_secret": has_webhook_secret,
        "credential_present": has_credential,
        "webhook_secret_present": has_webhook_secret,
        "outbound_write_enabled": connector.outbound_write_enabled,
        "action_contract": connector.action_contract,
        "config_version": connector.config_version,
        "version": connector.aggregate_version,
        "created_at": _iso(connector.created_at),
        "updated_at": _iso(connector.updated_at),
    }


def serialize_detail(connector: Connector) -> dict[str, Any]:
    payload = serialize_list_item(connector)
    payload["health_status"] = connector.health_status
    return payload


def serialize_delivery(observation: ExternalObservation) -> dict[str, Any]:
    return {
        "id": str(observation.id),
        "connector_id": str(observation.connector_id),
        "source": observation.source,
        "observation_key": observation.observation_key,
        "signature_ok": observation.signature_ok,
        "observed_at": _iso(observation.observed_at),
        "data_classification": observation.data_classification,
        "payload_ref": observation.payload_ref,
        "accepted": observation.signature_ok,
    }


def _parse_release_webhook_body(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body.decode("utf-8")) if body else {}
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_env_ref(settings: Settings, ref: str) -> str | None:
    if not ref.startswith("env:"):
        return None
    key = ref[4:]
    if key not in ALLOWED_ENV_REF_KEYS:
        return None
    if key == "GITHUB_WEBHOOK_SECRET":
        return settings.github_webhook_secret or None
    if key == "JENKINS_WEBHOOK_SECRET":
        return settings.jenkins_webhook_secret or None
    if key == "JENKINS_API_TOKEN":
        return settings.jenkins_api_token or None
    return None


def validate_credential_ref(ref: str) -> None:
    stripped = ref.strip()
    if not stripped:
        raise ValueError("validation")
    if SECRET_PATTERN.search(stripped) and not stripped.startswith("env:"):
        raise ValueError("validation")
    if not stripped.startswith("env:"):
        raise ValueError("validation")
    key = stripped[4:]
    if not key or key not in ALLOWED_ENV_REF_KEYS:
        raise ValueError("validation")


def verify_github_hmac(*, secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected_hex = signature_header[7:]
    if not expected_hex:
        return False
    computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if len(computed) != len(expected_hex):
        return False
    return hmac.compare_digest(computed, expected_hex)


def derive_observation_key(
    *,
    connector_id: uuid.UUID,
    body: bytes,
    delivery_id: str | None,
    event_type: str | None,
) -> str:
    if delivery_id and delivery_id.strip():
        external_id = delivery_id.strip()
    else:
        hasher = hashlib.sha256()
        hasher.update(body)
        if event_type:
            hasher.update(event_type.encode("utf-8"))
        external_id = hasher.hexdigest()
    return f"{connector_id}:{external_id}"


def payload_ref_from_body(body: bytes) -> str:
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


async def _require_owner_or_admin(session: AsyncSession, ctx: SessionContext) -> None:
    allowed = await identity_query.caller_is_owner_or_admin(
        session,
        organization_id=ctx.organization.id,
        user_id=ctx.user.id,
    )
    if not allowed:
        raise ValueError("forbidden")


async def list_connectors_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_type: str | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    if connector_type is not None and connector_type not in repo.VALID_CONNECTOR_TYPES:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")

    effective_limit = DEFAULT_LIST_LIMIT if limit is None else min(limit, MAX_LIST_LIMIT)
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    rows = await repo.list_connectors(
        session,
        organization_id=ctx.organization.id,
        connector_type=connector_type,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=effective_limit + 1,
    )
    has_more = len(rows) > effective_limit
    page_rows = rows[:effective_limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = repo.encode_created_id_cursor(
            created_at=last.created_at,
            item_id=last.id,
        )
    return {
        "items": [serialize_list_item(row) for row in page_rows],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def get_connector_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    connector = await repo.get_connector(
        session,
        organization_id=ctx.organization.id,
        connector_id=connector_id,
    )
    if connector is None:
        raise ValueError("not_found")
    return serialize_detail(connector)


async def list_webhook_deliveries_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
    signature_ok: bool | None,
    cursor: str | None,
    limit: int | None,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    connector = await repo.get_connector(
        session,
        organization_id=ctx.organization.id,
        connector_id=connector_id,
    )
    if connector is None:
        raise ValueError("not_found")
    if limit is not None and limit < 1:
        raise ValueError("validation")

    effective_limit = DEFAULT_LIST_LIMIT if limit is None else min(limit, MAX_LIST_LIMIT)
    cursor_observed_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_observed_at, cursor_id = repo.decode_observed_id_cursor(cursor)

    rows = await repo.list_observations_for_connector(
        session,
        organization_id=ctx.organization.id,
        connector_id=connector_id,
        signature_ok=signature_ok,
        cursor_observed_at=cursor_observed_at,
        cursor_id=cursor_id,
        limit=effective_limit + 1,
    )
    has_more = len(rows) > effective_limit
    page_rows = rows[:effective_limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = repo.encode_observed_id_cursor(
            observed_at=last.observed_at,
            item_id=last.id,
        )
    return {
        "items": [serialize_delivery(row) for row in page_rows],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def bind_credential_ref_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
    credential_ref: str,
    expected_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_BIND_CREDENTIAL,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    connector = await repo.get_connector(
        session,
        organization_id=org_id,
        connector_id=connector_id,
        for_update=True,
    )
    if connector is None:
        raise ValueError("not_found")

    validate_credential_ref(credential_ref)

    if expected_version is not None and connector.aggregate_version != expected_version:
        raise ValueError("version")

    connector.credential_ref = credential_ref.strip()
    connector.aggregate_version += 1
    connector.updated_at = now

    response = {
        "has_credential": True,
        "version": connector.aggregate_version,
    }

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="connector.credential_ref_bound",
            resource_type="connector",
            resource_id=connector.id,
            result="ok",
            request_hash=request_hash,
        ),
    )

    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_BIND_CREDENTIAL,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


async def process_inbound_webhook(
    session: AsyncSession,
    settings: Settings,
    *,
    connector_id: uuid.UUID,
    body: bytes,
    signature_header: str | None,
    delivery_id: str | None,
    event_type: str | None,
    request_hash: str,
) -> tuple[dict[str, Any], int, tuple[uuid.UUID, uuid.UUID] | None]:
    connector = await repo.get_connector_by_id(session, connector_id=connector_id)
    if connector is None:
        raise ValueError("not_found")

    org_id = connector.organization_id
    now = datetime.now(UTC)
    observation_key = derive_observation_key(
        connector_id=connector.id,
        body=body,
        delivery_id=delivery_id,
        event_type=event_type,
    )
    payload_ref = payload_ref_from_body(body)

    secret_ref = (connector.webhook_secret_ref or "").strip()
    resolved_secret = resolve_env_ref(settings, secret_ref) if secret_ref else None
    signature_ok = verify_github_hmac(
        secret=resolved_secret or "",
        body=body,
        signature_header=signature_header,
    )

    if not signature_ok:
        existing_failed = await repo.get_observation_by_key(
            session,
            organization_id=org_id,
            source=WEBHOOK_SOURCE,
            observation_key=observation_key,
        )
        if existing_failed is None:
            await repo.create_observation(
                session,
                organization_id=org_id,
                connector_id=connector.id,
                source=WEBHOOK_SOURCE,
                observation_key=observation_key,
                payload_ref=payload_ref,
                signature_ok=False,
                observed_at=now,
            )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=org_id,
                actor_user_id=None,
                action="inbound_webhook.hmac_failed",
                resource_type="connector",
                resource_id=connector.id,
                result="failed",
                request_hash=request_hash,
            ),
        )
        raise ValueError("hmac_failed")

    existing = await repo.get_observation_by_key(
        session,
        organization_id=org_id,
        source=WEBHOOK_SOURCE,
        observation_key=observation_key,
    )
    if existing is not None and existing.signature_ok:
        return (
            {
                "accepted": True,
                "observation_id": str(existing.id),
                "duplicate": True,
            },
            200,
            None,
        )
    if existing is not None:
        existing.signature_ok = True
        existing.payload_ref = payload_ref
        existing.observed_at = now
        await repo.create_inbox_event(
            session,
            organization_id=org_id,
            event_id=observation_key,
            consumer_name=repo.INBOUND_WEBHOOK_CONSUMER,
            processed_at=now,
            result_ref={"observation_id": str(existing.id)},
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=org_id,
                actor_user_id=None,
                action="inbound_webhook.accepted",
                resource_type="connector",
                resource_id=connector.id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        if connector.type == "release":
            from app.modules.release_orchestration import command_port as release_command

            release_body = _parse_release_webhook_body(body)
            await release_command.apply_release_observation(
                session,
                organization_id=org_id,
                body=release_body,
                request_hash=request_hash,
            )
            return (
                {
                    "accepted": True,
                    "observation_id": str(existing.id),
                    "duplicate": False,
                },
                202,
                None,
            )

        from app.modules.run_orchestration import command_port as run_command

        resume_run_id = await run_command.apply_ci_observation(
            session,
            organization_id=org_id,
            connector_id=connector.id,
            body=body,
            observation_id=existing.id,
            request_hash=request_hash,
        )
        resume = (org_id, resume_run_id) if resume_run_id is not None else None
        return (
            {
                "accepted": True,
                "observation_id": str(existing.id),
                "duplicate": False,
            },
            202,
            resume,
        )

    observation = await repo.create_observation(
        session,
        organization_id=org_id,
        connector_id=connector.id,
        source=WEBHOOK_SOURCE,
        observation_key=observation_key,
        payload_ref=payload_ref,
        signature_ok=True,
        observed_at=now,
    )
    await repo.create_inbox_event(
        session,
        organization_id=org_id,
        event_id=observation_key,
        consumer_name=repo.INBOUND_WEBHOOK_CONSUMER,
        processed_at=now,
        result_ref={"observation_id": str(observation.id)},
    )
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=None,
            action="inbound_webhook.accepted",
            resource_type="connector",
            resource_id=connector.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    if connector.type == "release":
        from app.modules.release_orchestration import command_port as release_command

        release_body = _parse_release_webhook_body(body)
        await release_command.apply_release_observation(
            session,
            organization_id=org_id,
            body=release_body,
            request_hash=request_hash,
        )
        return (
            {
                "accepted": True,
                "observation_id": str(observation.id),
                "duplicate": False,
            },
            202,
            None,
        )

    from app.modules.run_orchestration import command_port as run_command

    resume_run_id = await run_command.apply_ci_observation(
        session,
        organization_id=org_id,
        connector_id=connector.id,
        body=body,
        observation_id=observation.id,
        request_hash=request_hash,
    )
    resume = (org_id, resume_run_id) if resume_run_id is not None else None
    return (
        {
            "accepted": True,
            "observation_id": str(observation.id),
            "duplicate": False,
        },
        202,
        resume,
    )


def _generate_api_token_plaintext() -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    plaintext = f"{TOKEN_PREFIX_LITERAL}{secret}"
    prefix = plaintext[:TOKEN_PREFIX_DISPLAY_LEN]
    return plaintext, prefix


def _hash_api_token(plaintext: str) -> str:
    return PASSWORD_HASHER.hash(plaintext)


def serialize_api_token_list_item(token: ApiToken) -> dict[str, Any]:
    return {
        "id": str(token.id),
        "issued_to_user_id": str(token.issued_to_user_id),
        "token_prefix": token.token_prefix,
        "scopes": list(token.scopes),
        "project_ids": [str(pid) for pid in token.project_ids],
        "expires_at": _iso(token.expires_at),
        "revoked_at": _iso(token.revoked_at) if token.revoked_at else None,
        "last_used_at": _iso(token.last_used_at) if token.last_used_at else None,
        "created_at": _iso(token.created_at),
    }


def _issue_metadata_response(token: ApiToken) -> dict[str, Any]:
    return {
        "id": str(token.id),
        "token_prefix": token.token_prefix,
        "scopes": list(token.scopes),
        "project_ids": [str(pid) for pid in token.project_ids],
        "expires_at": _iso(token.expires_at),
        "revoked_at": _iso(token.revoked_at) if token.revoked_at else None,
    }


def _issue_response_with_token(token: ApiToken, plaintext: str) -> dict[str, Any]:
    payload = _issue_metadata_response(token)
    payload["token"] = plaintext
    return payload


def _validate_scopes(scopes: list[str]) -> None:
    if not scopes:
        raise ValueError("validation")
    if not all(scope in repo.VALID_API_TOKEN_SCOPES for scope in scopes):
        raise ValueError("validation")


def _validate_expires_at(expires_at: datetime, *, now: datetime) -> None:
    if expires_at.tzinfo is None:
        raise ValueError("validation")
    if expires_at <= now:
        raise ValueError("validation")


async def _validate_project_ids(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    project_ids: list[uuid.UUID],
) -> None:
    if not project_ids:
        raise ValueError("validation")
    for project_id in project_ids:
        role = await identity_query.get_project_membership_role(
            session,
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
        )
        if role is None:
            raise ValueError("not_found")


async def list_api_tokens_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    issued_to_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    if limit is not None and limit < 1:
        raise ValueError("validation")

    effective_limit = DEFAULT_LIST_LIMIT if limit is None else min(limit, MAX_LIST_LIMIT)
    cursor_created_at: datetime | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = repo.decode_created_id_cursor(cursor)

    rows = await repo.list_api_tokens(
        session,
        organization_id=ctx.organization.id,
        issued_to_user_id=issued_to_user_id,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=effective_limit + 1,
    )
    has_more = len(rows) > effective_limit
    page_rows = rows[:effective_limit]
    next_cursor = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = repo.encode_created_id_cursor(
            created_at=last.created_at,
            item_id=last.id,
        )
    return {
        "items": [serialize_api_token_list_item(row) for row in page_rows],
        "page": {"next_cursor": next_cursor, "has_more": has_more},
    }


async def issue_api_token_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    scopes: list[str],
    project_ids: list[uuid.UUID],
    expires_at: datetime,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_ISSUE_TOKEN,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return dict(existing.response_ref)

    _validate_scopes(scopes)
    _validate_expires_at(expires_at, now=now)
    await _validate_project_ids(
        session,
        organization_id=org_id,
        user_id=ctx.user.id,
        project_ids=project_ids,
    )

    plaintext, prefix = _generate_api_token_plaintext()
    token_hash = _hash_api_token(plaintext)

    token = await repo.create_api_token(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=ctx.user.id,
        issued_to_user_id=ctx.user.id,
        token_hash=token_hash,
        token_prefix=prefix,
        scopes=scopes,
        project_ids=project_ids,
        expires_at=expires_at,
    )

    response_with_token = _issue_response_with_token(token, plaintext)
    stored_ref = _issue_metadata_response(token)

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="api_token.issued",
            resource_type="api_token",
            resource_id=token.id,
            result="ok",
            request_hash=request_hash,
        ),
    )

    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_ISSUE_TOKEN,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=stored_ref,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response_with_token


async def revoke_api_token_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    api_token_id: uuid.UUID,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_REVOKE_TOKEN,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    token = await repo.get_api_token(
        session,
        organization_id=org_id,
        api_token_id=api_token_id,
        for_update=True,
    )
    if token is None:
        raise ValueError("not_found")

    if token.revoked_at is None:
        token.revoked_at = now
        token.updated_at = now

    response = serialize_api_token_list_item(token)

    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="api_token.revoked",
            resource_type="api_token",
            resource_id=token.id,
            result="ok",
            request_hash=request_hash,
        ),
    )

    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_REVOKE_TOKEN,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return response


async def authenticate_api_token(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    raw_token: str,
) -> ApiToken | None:
    prefix = _token_prefix(raw_token)
    if prefix is None:
        return None
    return await _verify_token_candidates(
        await repo.list_api_tokens_by_prefix(
            session,
            organization_id=organization_id,
            token_prefix=prefix,
        ),
        raw_token=raw_token,
    )


async def authenticate_api_token_by_prefix(
    session: AsyncSession,
    *,
    raw_token: str,
) -> ApiToken | None:
    prefix = _token_prefix(raw_token)
    if prefix is None:
        return None
    return await _verify_token_candidates(
        await repo.list_api_tokens_by_prefix_global(session, token_prefix=prefix),
        raw_token=raw_token,
    )


def _token_prefix(raw_token: str) -> str | None:
    if not raw_token.startswith(TOKEN_PREFIX_LITERAL):
        return None
    if len(raw_token) < TOKEN_PREFIX_DISPLAY_LEN:
        return None
    return raw_token[:TOKEN_PREFIX_DISPLAY_LEN]


async def _verify_token_candidates(
    candidates: list[ApiToken],
    *,
    raw_token: str,
) -> ApiToken | None:
    now = datetime.now(UTC)
    for token in candidates:
        if token.revoked_at is not None:
            continue
        expires = token.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= now:
            continue
        try:
            PASSWORD_HASHER.verify(token.token_hash, raw_token)
            return token
        except VerifyMismatchError:
            continue
    return None


async def _require_project_owner_or_admin(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
) -> None:
    if not await identity_query.project_exists_in_org(
        session, organization_id=ctx.organization.id, project_id=project_id
    ):
        raise ValueError("not_found")
    role = await identity_query.get_project_membership_role(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if role is None:
        raise ValueError("not_found")
    if role not in {"owner", "admin"}:
        raise ValueError("forbidden")


def _validate_connector_type(connector_type: str) -> None:
    if connector_type not in repo.VALID_CONNECTOR_TYPES:
        raise ValueError("validation")


async def create_connector_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_type: str,
    name: str,
    auth_method: str,
    action_contract: dict[str, Any],
    has_credential_binding: bool | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTOR_REGISTER,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return {"data": existing.response_ref}

    _validate_connector_type(connector_type)
    if not name.strip() or not auth_method.strip():
        raise ValueError("validation")
    if not isinstance(action_contract, dict):
        raise ValueError("validation")

    connector = await repo.create_connector(
        session,
        organization_id=org_id,
        created_at=now,
        created_by=ctx.user.id,
        connector_type=connector_type,
        name=name.strip(),
        auth_method=auth_method.strip(),
        credential_ref="bound" if has_credential_binding else "",
        action_contract=action_contract,
    )
    response = serialize_list_item(connector)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="connector.register",
            resource_type="connector",
            resource_id=connector.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTOR_REGISTER,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return {"data": response}


async def patch_connector_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
    expected_version: int,
    name: str | None,
    action_contract: dict[str, Any] | None,
    outbound_write_enabled: bool | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTOR_PATCH,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return {"data": existing.response_ref}

    connector = await repo.get_connector(
        session,
        organization_id=org_id,
        connector_id=connector_id,
        for_update=True,
    )
    if connector is None:
        raise ValueError("not_found")
    if connector.aggregate_version != expected_version:
        raise ValueError("version")

    if outbound_write_enabled is True and not connector.outbound_write_enabled:
        raise ValueError("policy_deny")
    if name is not None:
        if not name.strip():
            raise ValueError("validation")
        connector.name = name.strip()
    if action_contract is not None:
        if not isinstance(action_contract, dict):
            raise ValueError("validation")
        connector.action_contract = action_contract
    if outbound_write_enabled is not None:
        connector.outbound_write_enabled = outbound_write_enabled
    connector.aggregate_version += 1
    connector.config_version += 1
    connector.updated_at = now

    response = serialize_list_item(connector)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="connector.patch",
            resource_type="connector",
            resource_id=connector.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CONNECTOR_PATCH,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return {"data": response}


def _validate_outbound_channel_kind(kind: str) -> str:
    stripped = kind.strip()
    if not stripped or len(stripped) > 64:
        raise ValueError("validation")
    if not OUTBOUND_KIND_PATTERN.match(stripped):
        raise ValueError("validation")
    return stripped


def _validate_outbound_endpoint_ref(ref: str) -> str:
    stripped = ref.strip()
    if not stripped:
        raise ValueError("validation")
    lowered = stripped.lower()
    if "http://" in lowered or "https://" in lowered:
        raise ValueError("validation")
    if SECRET_PATTERN.search(stripped) and not stripped.startswith("env:"):
        raise ValueError("validation")
    if not OUTBOUND_ENV_REF_PATTERN.match(stripped):
        raise ValueError("validation")
    return stripped


def _serialize_outbound_channel_item(channel: dict[str, Any]) -> dict[str, Any]:
    endpoint_ref = channel.get("endpoint_ref", "")
    endpoint_present = bool(isinstance(endpoint_ref, str) and endpoint_ref.strip())
    return {
        "id": str(channel["id"]),
        "enabled": True,
        "is_primary": bool(channel.get("is_primary")),
        "channel_type": str(channel["kind"]),
        "endpoint_present": endpoint_present,
    }


def _serialize_outbound_channels_payload(
    connector: Connector,
) -> dict[str, Any]:
    channels = connector.outbound_channels if isinstance(connector.outbound_channels, list) else []
    return {
        "items": [_serialize_outbound_channel_item(item) for item in channels],
        "connector_version": connector.aggregate_version,
    }


async def list_outbound_channels_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    connector = await repo.get_connector(
        session,
        organization_id=ctx.organization.id,
        connector_id=connector_id,
    )
    if connector is None:
        raise ValueError("not_found")
    return _serialize_outbound_channels_payload(connector)


async def put_outbound_channels_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    connector_id: uuid.UUID,
    expected_version: int,
    channels: list[dict[str, Any]],
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_owner_or_admin(session, ctx)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_OUTBOUND_CHANNELS,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return {"data": existing.response_ref}

    connector = await repo.get_connector(
        session,
        organization_id=org_id,
        connector_id=connector_id,
        for_update=True,
    )
    if connector is None:
        raise ValueError("not_found")
    if connector.aggregate_version != expected_version:
        raise ValueError("version")

    normalized: list[dict[str, Any]] = []
    primary_count = 0
    for item in channels:
        if not isinstance(item, dict):
            raise ValueError("validation")
        kind_raw = item.get("kind")
        if not isinstance(kind_raw, str):
            raise ValueError("validation")
        kind = _validate_outbound_channel_kind(kind_raw)
        is_primary = item.get("is_primary")
        if not isinstance(is_primary, bool):
            raise ValueError("validation")
        if is_primary:
            primary_count += 1
        endpoint_ref = ""
        if "endpoint_ref" in item and item["endpoint_ref"] is not None:
            if not isinstance(item["endpoint_ref"], str):
                raise ValueError("validation")
            endpoint_ref = _validate_outbound_endpoint_ref(item["endpoint_ref"])
        normalized.append(
            {
                "id": str(uuid.uuid4()),
                "kind": kind,
                "is_primary": is_primary,
                "endpoint_ref": endpoint_ref,
            }
        )

    if normalized and primary_count != 1:
        raise ValueError("validation")

    connector.outbound_channels = normalized
    connector.aggregate_version += 1
    connector.config_version += 1
    connector.updated_at = now

    response = _serialize_outbound_channels_payload(connector)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="connector.put_outbound_channels",
            resource_type="connector",
            resource_id=connector.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_OUTBOUND_CHANNELS,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return {"data": response}


def _serialize_ci_trigger_bindings(row: ProjectCiTriggerConfig) -> dict[str, Any]:
    return {
        "project_id": str(row.project_id),
        "version": row.aggregate_version,
        "bindings": list(row.bindings),
        "updated_at": _iso(row.updated_at),
    }


async def put_ci_trigger_bindings_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    expected_version: int,
    bindings: list[dict[str, Any]],
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    await _require_project_owner_or_admin(session, ctx, project_id=project_id)
    org_id = ctx.organization.id
    now = datetime.now(UTC)

    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CI_TRIGGER_BINDINGS,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return {"data": existing.response_ref}

    normalized: list[dict[str, Any]] = []
    for item in bindings:
        if not isinstance(item, dict):
            raise ValueError("validation")
        repository = item.get("repository")
        ref_pattern = item.get("ref_pattern")
        test_plan_id = item.get("test_plan_id")
        if not isinstance(repository, str) or not repository.strip():
            raise ValueError("validation")
        if not isinstance(ref_pattern, str) or not ref_pattern.strip():
            raise ValueError("validation")
        try:
            plan_uuid = uuid.UUID(str(test_plan_id))
        except (TypeError, ValueError) as exc:  # fmt: skip
            raise ValueError("validation") from exc
        entry: dict[str, Any] = {
            "repository": repository.strip(),
            "ref_pattern": ref_pattern.strip(),
            "test_plan_id": str(plan_uuid),
        }
        connector_id = item.get("connector_id")
        if connector_id is not None:
            try:
                entry["connector_id"] = str(uuid.UUID(str(connector_id)))
            except (TypeError, ValueError) as exc:  # fmt: skip
                raise ValueError("validation") from exc
        normalized.append(entry)

    row = await repo.upsert_ci_trigger_config(
        session,
        organization_id=org_id,
        project_id=project_id,
        bindings=normalized,
        expected_version=expected_version,
        created_by=ctx.user.id,
        now=now,
    )
    response = _serialize_ci_trigger_bindings(row)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="project.put_ci_trigger_bindings",
            resource_type="project",
            resource_id=project_id,
            project_id=project_id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CI_TRIGGER_BINDINGS,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
        created_at=now,
    )
    return {"data": response}
