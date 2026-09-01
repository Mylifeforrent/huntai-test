import hashlib
import hmac
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy.service import SessionContext
from app.modules.integration_hub import repository as repo
from app.modules.integration_hub.models import Connector, ExternalObservation
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event

COMMAND_TYPE_BIND_CREDENTIAL = "connector.bind_credential_ref"
ALLOWED_ENV_REF_KEYS = frozenset({"GITHUB_WEBHOOK_SECRET"})
SECRET_PATTERN = re.compile(
    r"(password|secret|token|credential)",
    re.IGNORECASE,
)
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
    return {
        "id": str(connector.id),
        "type": connector.type,
        "name": connector.name,
        "auth_method": connector.auth_method,
        "credential_present": _credential_present(connector),
        "webhook_secret_present": _webhook_secret_present(connector),
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


def resolve_env_ref(settings: Settings, ref: str) -> str | None:
    if not ref.startswith("env:"):
        return None
    key = ref[4:]
    if key not in ALLOWED_ENV_REF_KEYS:
        return None
    if key == "GITHUB_WEBHOOK_SECRET":
        value = settings.github_webhook_secret
        return value if value else None
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
) -> tuple[dict[str, Any], int]:
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
        return (
            {
                "accepted": True,
                "observation_id": str(existing.id),
                "duplicate": False,
            },
            202,
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
    return (
        {
            "accepted": True,
            "observation_id": str(observation.id),
            "duplicate": False,
        },
        202,
    )
