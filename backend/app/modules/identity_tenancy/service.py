import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.models import AuthSession, Organization, User
from app.modules.results_evidence.audit_port import AuditAppendInput, append_audit_event


@dataclass(frozen=True)
class SessionContext:
    session: AuthSession
    user: User
    organization: Organization


def validate_return_path(return_path: str | None) -> str:
    if return_path is None:
        return "/"
    if not return_path.startswith("/"):
        raise ValueError("invalid_return_path")
    if return_path.startswith("//"):
        raise ValueError("invalid_return_path")
    if "://" in return_path:
        raise ValueError("invalid_return_path")
    return return_path


def compute_reauth_required(
    session: AuthSession, *, reauth_window_seconds: int, now: datetime | None = None
) -> bool:
    current = now or datetime.now(UTC)
    anchor = session.last_reauth_at or session.created_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    return (current - anchor).total_seconds() > reauth_window_seconds


async def load_session_context(
    session: AsyncSession, auth_session: AuthSession
) -> SessionContext | None:
    now = datetime.now(UTC)
    if auth_session.revoked_at is not None:
        return None
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if now >= expires_at:
        return None

    user = await repo.get_user_by_id(session, auth_session.user_id)
    if user is None or user.is_disabled:
        return None

    organization = await repo.get_organization_by_id(session, auth_session.organization_id)
    if organization is None:
        return None

    return SessionContext(session=auth_session, user=user, organization=organization)


async def start_oidc_flow(
    session: AsyncSession,
    settings: Settings,
    *,
    return_path: str | None,
) -> dict[str, str]:
    normalized_path = validate_return_path(return_path)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier, code_challenge = repo.generate_pkce_pair()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.oidc_login_draft_ttl_seconds)
    await repo.create_oidc_draft(
        session,
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        return_path=normalized_path,
        expires_at=expires_at,
    )
    authorization_url = build_authorization_url(
        settings,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
    )
    return {"authorization_url": authorization_url}


def build_authorization_url(
    settings: Settings,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorize_endpoint = f"{settings.oidc_issuer.rstrip('/')}/authorize"
    return f"{authorize_endpoint}?{urlencode(params)}"


async def exchange_oidc_code(
    settings: Settings,
    *,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    token_endpoint = f"{settings.oidc_issuer.rstrip('/')}/token"
    async with AsyncOAuth2Client(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
    ) as client:
        token = await client.fetch_token(
            token_endpoint,
            code=code,
            grant_type="authorization_code",
            redirect_uri=settings.oidc_redirect_uri,
            code_verifier=code_verifier,
        )
    return dict(token)


async def verify_id_token(
    settings: Settings,
    *,
    id_token: str,
    expected_nonce: str,
) -> dict[str, Any]:
    metadata_url = f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        metadata_response = await client.get(metadata_url)
        metadata_response.raise_for_status()
        metadata: dict[str, Any] = metadata_response.json()
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri:
            raise ValueError("missing_jwks_uri")
        jwks_response = await client.get(jwks_uri)
        jwks_response.raise_for_status()
        jwks_data: dict[str, Any] = jwks_response.json()

    key_set = JsonWebKey.import_key_set(jwks_data)
    claims = jose_jwt.decode(id_token, key_set)
    claims.validate()
    if claims.get("nonce") != expected_nonce:
        raise ValueError("nonce_mismatch")
    return dict(claims)


async def complete_oidc_callback(
    session: AsyncSession,
    settings: Settings,
    *,
    code: str,
    state: str,
    existing_session: AuthSession | None,
) -> tuple[AuthSession, str]:
    draft = await repo.get_oidc_draft_by_state(session, state)
    now = datetime.now(UTC)
    if (
        draft is None
        or draft.consumed_at is not None
        or (
            draft.expires_at.replace(tzinfo=UTC)
            if draft.expires_at.tzinfo is None
            else draft.expires_at
        )
        < now
    ):
        raise ValueError("oidc_draft_invalid")

    token_response = await exchange_oidc_code(
        settings, code=code, code_verifier=draft.code_verifier
    )
    id_token = token_response.get("id_token")
    if not isinstance(id_token, str):
        raise ValueError("missing_id_token")

    claims = await verify_id_token(settings, id_token=id_token, expected_nonce=draft.nonce)

    subject_claim = settings.oidc_claim_subject
    idp_subject = claims.get(subject_claim)
    if not isinstance(idp_subject, str) or not idp_subject:
        raise ValueError("missing_subject")

    users = await repo.find_users_by_idp_subject(session, idp_subject)
    if len(users) != 1:
        raise ValueError("no_org_context")

    user = users[0]
    if user.is_disabled:
        raise ValueError("user_disabled")

    expires_at = now + timedelta(seconds=settings.session_ttl_seconds)
    is_reauth = existing_session is not None and existing_session.revoked_at is None

    if is_reauth and existing_session is not None:
        await repo.revoke_auth_session(session, existing_session)
        auth_session = await repo.create_auth_session(
            session,
            organization_id=user.organization_id,
            user_id=user.id,
            expires_at=expires_at,
            last_reauth_at=now,
        )
    else:
        auth_session = await repo.create_auth_session(
            session,
            organization_id=user.organization_id,
            user_id=user.id,
            expires_at=expires_at,
            last_reauth_at=None,
        )

    await repo.consume_oidc_draft(session, draft)
    return_path = draft.return_path or "/"
    return auth_session, return_path


async def logout_session(
    session: AsyncSession,
    *,
    ctx: SessionContext | None,
    raw_session_id: uuid.UUID | None,
    idempotency_key: str | None,
    request_hash: str,
) -> None:
    if ctx is None:
        if raw_session_id is not None:
            row = await repo.get_auth_session_by_id(session, raw_session_id)
            if row is not None:
                await repo.revoke_auth_session(session, row)
        return

    if idempotency_key is not None:
        existing = await repo.get_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="session.logout",
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ValueError("idempotency_conflict")
            return

    await repo.revoke_auth_session(session, ctx.session)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=ctx.organization.id,
            actor_user_id=ctx.user.id,
            action="session.logout",
            resource_type="auth_session",
            resource_id=ctx.session.id,
            result="ok",
            request_hash=request_hash,
        ),
    )

    if idempotency_key is not None:
        await repo.create_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="session.logout",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref={"logged_out": True},
            created_by=ctx.user.id,
        )


def build_me_payload(ctx: SessionContext, memberships: list[repo.MembershipRow]) -> dict[str, Any]:
    settings = get_settings()
    org = ctx.organization
    return {
        "user": {
            "id": str(ctx.user.id),
            "display_name": ctx.user.display_name or "",
            "email": ctx.user.email,
            "is_disabled": ctx.user.is_disabled,
        },
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "version": org.aggregate_version,
            "is_active": org.is_active,
            "capability_controls": org.capability_controls,
        },
        "memberships": [
            {
                "project_id": str(m.project_id),
                "project_name": m.project_name,
                "role": m.role,
            }
            for m in memberships
        ],
        "reauth_required": compute_reauth_required(
            ctx.session, reauth_window_seconds=settings.reauth_window_seconds
        ),
    }


def build_organization_current(org: Organization) -> dict[str, Any]:
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "version": org.aggregate_version,
        "is_active": org.is_active,
        "capability_controls": org.capability_controls,
        "created_at": org.created_at.isoformat(),
        "updated_at": org.updated_at.isoformat(),
    }


def build_session_payload(ctx: SessionContext) -> dict[str, Any]:
    settings = get_settings()
    expires_at = ctx.session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return {
        "expires_at": expires_at.isoformat(),
        "reauth_required": compute_reauth_required(
            ctx.session, reauth_window_seconds=settings.reauth_window_seconds
        ),
    }
