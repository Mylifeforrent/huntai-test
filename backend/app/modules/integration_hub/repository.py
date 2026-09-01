import base64
import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration_hub.models import (
    ApiToken,
    CommandIdempotencyRecord,
    Connector,
    ExternalObservation,
    InboxEvent,
)

VALID_CONNECTOR_TYPES = frozenset({"jira", "github", "ci", "release"})
VALID_API_TOKEN_SCOPES = frozenset({"read", "write", "execute", "delete"})
INBOUND_WEBHOOK_CONSUMER = "inbound_webhook"


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def encode_observed_id_cursor(*, observed_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": observed_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_observed_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        observed_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return observed_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


def encode_created_id_cursor(*, created_at: datetime, item_id: uuid.UUID) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "i": str(item_id)},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_created_id_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        created_at = datetime.fromisoformat(data["t"])
        item_id = uuid.UUID(data["i"])
        return created_at, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


async def get_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_id: uuid.UUID,
    for_update: bool = False,
) -> Connector | None:
    query = select(Connector).where(
        Connector.organization_id == organization_id,
        Connector.id == connector_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_connector_by_id(
    session: AsyncSession,
    *,
    connector_id: uuid.UUID,
    for_update: bool = False,
) -> Connector | None:
    query = select(Connector).where(Connector.id == connector_id)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_connectors(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_type: str | None,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int | None,
) -> list[Connector]:
    query = select(Connector).where(Connector.organization_id == organization_id)
    if connector_type is not None:
        query = query.where(Connector.type == connector_type)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                Connector.created_at < cursor_created_at,
                and_(
                    Connector.created_at == cursor_created_at,
                    Connector.id < cursor_id,
                ),
            )
        )
    query = query.order_by(Connector.created_at.desc(), Connector.id.desc())
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    connector_type: str,
    name: str,
    auth_method: str = "hmac",
    credential_ref: str = "",
    action_contract: dict[str, Any] | None = None,
    outbound_write_enabled: bool = False,
    webhook_secret_ref: str | None = None,
    config_version: int = 1,
    health_status: dict[str, Any] | None = None,
) -> Connector:
    connector = Connector(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        aggregate_version=1,
        type=connector_type,
        name=name,
        auth_method=auth_method,
        credential_ref=credential_ref,
        action_contract=action_contract if action_contract is not None else {},
        outbound_write_enabled=outbound_write_enabled,
        webhook_secret_ref=webhook_secret_ref,
        standing_auth_metadata=None,
        config_version=config_version,
        health_status=health_status,
    )
    session.add(connector)
    await session.flush()
    return connector


async def get_observation_by_key(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    source: str,
    observation_key: str,
) -> ExternalObservation | None:
    result = await session.execute(
        select(ExternalObservation).where(
            ExternalObservation.organization_id == organization_id,
            ExternalObservation.source == source,
            ExternalObservation.observation_key == observation_key,
        )
    )
    return result.scalar_one_or_none()


async def create_observation(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_id: uuid.UUID,
    source: str,
    observation_key: str,
    payload_ref: str | None,
    signature_ok: bool,
    observed_at: datetime,
    data_classification: str = "Internal",
) -> ExternalObservation:
    observation = ExternalObservation(
        id=uuid.uuid4(),
        organization_id=organization_id,
        source=source,
        connector_id=connector_id,
        observation_key=observation_key,
        payload_ref=payload_ref,
        signature_ok=signature_ok,
        observed_at=observed_at,
        data_classification=data_classification,
    )
    session.add(observation)
    await session.flush()
    return observation


async def create_inbox_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_id: str,
    consumer_name: str,
    processed_at: datetime | None,
    result_ref: dict[str, Any] | None,
) -> InboxEvent:
    row = InboxEvent(
        id=uuid.uuid4(),
        organization_id=organization_id,
        event_id=event_id,
        consumer_name=consumer_name,
        processed_at=processed_at,
        result_ref=result_ref,
    )
    session.add(row)
    await session.flush()
    return row


async def list_observations_for_connector(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connector_id: uuid.UUID,
    signature_ok: bool | None,
    cursor_observed_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int | None,
) -> list[ExternalObservation]:
    query = select(ExternalObservation).where(
        ExternalObservation.organization_id == organization_id,
        ExternalObservation.connector_id == connector_id,
    )
    if signature_ok is not None:
        query = query.where(ExternalObservation.signature_ok == signature_ok)
    if cursor_observed_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                ExternalObservation.observed_at < cursor_observed_at,
                and_(
                    ExternalObservation.observed_at == cursor_observed_at,
                    ExternalObservation.id < cursor_id,
                ),
            )
        )
    query = query.order_by(
        ExternalObservation.observed_at.desc(),
        ExternalObservation.id.desc(),
    )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
) -> CommandIdempotencyRecord | None:
    result = await session.execute(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.organization_id == organization_id,
            CommandIdempotencyRecord.command_type == command_type,
            CommandIdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def create_idempotency_record(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    command_type: str,
    idempotency_key: str,
    request_hash: str,
    response_ref: dict[str, Any],
    created_by: uuid.UUID | None,
    created_at: datetime,
) -> CommandIdempotencyRecord:
    record = CommandIdempotencyRecord(
        id=uuid.uuid4(),
        organization_id=organization_id,
        command_type=command_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response_ref,
        created_at=created_at,
        created_by=created_by,
    )
    session.add(record)
    await session.flush()
    return record


async def create_api_token(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_at: datetime,
    created_by: uuid.UUID | None,
    issued_to_user_id: uuid.UUID,
    token_hash: str,
    token_prefix: str,
    scopes: list[str],
    project_ids: list[uuid.UUID],
    expires_at: datetime,
) -> ApiToken:
    token = ApiToken(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=created_at,
        updated_at=created_at,
        created_by=created_by,
        issued_to_user_id=issued_to_user_id,
        token_hash=token_hash,
        token_prefix=token_prefix,
        scopes=scopes,
        project_ids=project_ids,
        expires_at=expires_at,
        revoked_at=None,
        last_used_at=None,
    )
    session.add(token)
    await session.flush()
    return token


async def get_api_token(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    api_token_id: uuid.UUID,
    for_update: bool = False,
) -> ApiToken | None:
    query = select(ApiToken).where(
        ApiToken.organization_id == organization_id,
        ApiToken.id == api_token_id,
    )
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_api_tokens_by_prefix(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    token_prefix: str,
) -> list[ApiToken]:
    result = await session.execute(
        select(ApiToken).where(
            ApiToken.organization_id == organization_id,
            ApiToken.token_prefix == token_prefix,
        )
    )
    return list(result.scalars().all())


async def list_api_tokens(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    issued_to_user_id: uuid.UUID | None,
    cursor_created_at: datetime | None,
    cursor_id: uuid.UUID | None,
    limit: int | None,
) -> list[ApiToken]:
    query = select(ApiToken).where(ApiToken.organization_id == organization_id)
    if issued_to_user_id is not None:
        query = query.where(ApiToken.issued_to_user_id == issued_to_user_id)
    if cursor_created_at is not None and cursor_id is not None:
        query = query.where(
            or_(
                ApiToken.created_at < cursor_created_at,
                and_(
                    ApiToken.created_at == cursor_created_at,
                    ApiToken.id < cursor_id,
                ),
            )
        )
    query = query.order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())
