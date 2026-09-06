import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.approval_policy import query_port as approval_query
from app.modules.identity_tenancy import query_port as identity_query
from app.modules.identity_tenancy import repository as repo
from app.modules.identity_tenancy.models import (
    DEFAULT_CAPABILITY_CONTROLS,
    DEFAULT_SIEM_EXPORT,
    AuthSession,
    Organization,
    Project,
    ProjectMember,
    User,
)
from app.modules.results_evidence.audit_port import (
    AuditAppendInput,
    append_audit_event,
    list_recent_for_project,
)
from app.modules.run_orchestration import query_port as run_query

WORKBENCH_LIST_LIMIT = 50
OIDC_FAILURE_QUERY_KEY = "oidc"
OIDC_FAILURE_QUERY_VALUE = "failed"
OIDC_PROMPT_LOGIN = "login"


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
    path_only = return_path.split("?", 1)[0]
    if path_only == "/api" or path_only.startswith("/api/"):
        raise ValueError("invalid_return_path")
    return return_path


def strip_oidc_failure_marker(return_path: str) -> str:
    parsed = urlparse(return_path)
    pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != OIDC_FAILURE_QUERY_KEY
    ]
    query = urlencode(pairs)
    path = parsed.path or "/"
    return f"{path}?{query}" if query else path


def append_oidc_failure_marker(return_path: str) -> str:
    cleaned = strip_oidc_failure_marker(return_path)
    parsed = urlparse(cleaned)
    pairs = list(parse_qsl(parsed.query, keep_blank_values=True))
    pairs.append((OIDC_FAILURE_QUERY_KEY, OIDC_FAILURE_QUERY_VALUE))
    path = parsed.path or "/"
    return f"{path}?{urlencode(pairs)}"


def normalize_oidc_prompt(prompt: str | None) -> str | None:
    if prompt is None or prompt == "":
        return None
    if prompt != OIDC_PROMPT_LOGIN:
        raise ValueError("invalid_prompt")
    return OIDC_PROMPT_LOGIN


async def resolve_oidc_failure_location(session: AsyncSession, state: str | None) -> str:
    return_path = "/"
    if state:
        draft = await repo.get_oidc_draft_by_state(session, state)
        if draft is not None and draft.return_path:
            try:
                return_path = validate_return_path(draft.return_path)
            except ValueError:
                return_path = "/"
    return append_oidc_failure_marker(return_path)


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
    prompt: str | None = None,
) -> dict[str, str]:
    normalized_prompt = normalize_oidc_prompt(prompt)
    normalized_path = strip_oidc_failure_marker(validate_return_path(return_path))
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
        prompt=normalized_prompt,
    )
    return {"authorization_url": authorization_url}


def build_authorization_url(
    settings: Settings,
    *,
    state: str,
    nonce: str,
    code_challenge: str,
    prompt: str | None = None,
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
    if prompt == OIDC_PROMPT_LOGIN:
        params["prompt"] = OIDC_PROMPT_LOGIN
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
            "siem_export_enabled": siem_export_enabled(org),
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
        "siem_export_enabled": siem_export_enabled(org),
        "created_at": org.created_at.isoformat(),
        "updated_at": org.updated_at.isoformat(),
    }


def siem_export_enabled(org: Organization) -> bool:
    export = org.siem_export or DEFAULT_SIEM_EXPORT
    return bool(export.get("enabled", False))


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


def is_last_owner_violation(
    *, current_role: str, target_role: str | None, owner_count: int
) -> bool:
    """Return True when demoting/removing would leave the project with zero owners.

    ``target_role`` is None for remove; otherwise the new role after patch.
    """
    if current_role != "owner":
        return False
    if target_role == "owner":
        return False
    return owner_count <= 1


def require_idempotency_key(raw: str | None) -> str:
    if raw is None or not raw.strip():
        raise ValueError("validation")
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError as exc:
        raise ValueError("validation") from exc


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def build_project_list_item(row: repo.ProjectListRow) -> dict[str, Any]:
    project = row.project
    return {
        "id": str(project.id),
        "name": project.name,
        "version": project.aggregate_version,
        "my_role": row.my_role,
        "jira_project_key": project.jira_project_key,
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
    }


def build_project_member_payload(
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    display_name: str | None,
) -> dict[str, Any]:
    return {
        "project_id": str(project_id),
        "user_id": str(user_id),
        "role": role,
        "display_name": display_name or "",
    }


async def list_projects(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    cursor: str | None,
    limit: int | None,
    q: str | None,
    sort: str | None,
) -> dict[str, Any]:
    if sort is not None:
        raise ValueError("validation")
    if limit is not None and limit < 1:
        raise ValueError("validation")

    cursor_name: str | None = None
    cursor_id: uuid.UUID | None = None
    if cursor is not None:
        cursor_name, cursor_id = repo.decode_name_id_cursor(cursor)

    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_member_projects(
        session,
        organization_id=ctx.organization.id,
        user_id=ctx.user.id,
        q=q,
        cursor_name=cursor_name,
        cursor_id=cursor_id,
        fetch_limit=fetch_limit,
    )

    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]

    items = [build_project_list_item(row) for row in rows]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = repo.encode_name_id_cursor(name=last.project.name, item_id=last.project.id)

    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    if limit is not None:
        page["limit"] = limit
    return {"data": {"items": items}, "page": page}


async def get_project_overview(
    session: AsyncSession, ctx: SessionContext, *, project_id: uuid.UUID
) -> dict[str, Any]:
    project = await repo.get_project(
        session, organization_id=ctx.organization.id, project_id=project_id
    )
    member = await repo.get_project_member(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if project is None or member is None:
        raise ValueError("not_found")

    events = await list_recent_for_project(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        limit=50,
    )
    recent_activity = [
        {
            "occurred_at": _iso(event.created_at),
            "summary": event.action or "",
            "resource_type": event.resource_type,
            "resource_id": str(event.resource_id) if event.resource_id else None,
            "audit_event_id": str(event.id),
        }
        for event in events
    ]
    bind_env_ids = [str(env_id) for env_id in (project.bind_env_ids or [])]
    return {
        "id": str(project.id),
        "name": project.name,
        "version": project.aggregate_version,
        "my_role": member.role,
        "jira": {"project_key": project.jira_project_key},
        "bind_env_ids": bind_env_ids,
        "connector_health": [],
        "recent_activity": recent_activity,
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
    }


async def list_members(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    cursor: str | None,
    limit: int | None,
    role: str | None,
) -> dict[str, Any]:
    if limit is not None and limit < 1:
        raise ValueError("validation")
    if role is not None and role not in repo.PROJECT_ROLES:
        raise ValueError("validation")

    project = await repo.get_project(
        session, organization_id=ctx.organization.id, project_id=project_id
    )
    caller = await repo.get_project_member(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if project is None or caller is None:
        raise ValueError("not_found")

    cursor_id = repo.decode_uuid_cursor(cursor) if cursor is not None else None
    fetch_limit = None if limit is None else limit + 1
    rows = await repo.list_project_members(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        role=role,
        cursor_id=cursor_id,
        fetch_limit=fetch_limit,
    )

    has_more = False
    if limit is not None and len(rows) > limit:
        has_more = True
        rows = rows[:limit]

    include_email = caller.role in repo.WRITE_ROLES
    items: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            "user_id": str(row.member.user_id),
            "role": row.member.role,
            "display_name": row.display_name or "",
            "created_at": _iso(row.member.created_at),
            "updated_at": _iso(row.member.updated_at),
        }
        if include_email:
            item["email"] = row.email
        items.append(item)

    next_cursor = None
    if has_more and rows:
        next_cursor = repo.encode_uuid_cursor(rows[-1].member.user_id)
    page: dict[str, Any] = {"next_cursor": next_cursor, "has_more": has_more}
    if limit is not None:
        page["limit"] = limit
    return {"data": {"items": items}, "page": page}


async def _resolve_writable_project(
    session: AsyncSession, ctx: SessionContext, *, project_id: uuid.UUID
) -> tuple[Project, ProjectMember]:
    project = await repo.get_project(
        session, organization_id=ctx.organization.id, project_id=project_id
    )
    caller = await repo.get_project_member(
        session,
        organization_id=ctx.organization.id,
        project_id=project_id,
        user_id=ctx.user.id,
    )
    if project is None or caller is None:
        raise ValueError("not_found")
    if caller.role not in repo.WRITE_ROLES:
        raise ValueError("forbidden")
    return project, caller


def _check_expected_version(project: Project, expected: int | None) -> None:
    if expected is None:
        return
    if expected != project.aggregate_version:
        raise ValueError("version_conflict")


async def add_project_member(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    expected_project_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    if role not in repo.PROJECT_ROLES:
        raise ValueError("validation")

    project, _caller = await _resolve_writable_project(session, ctx, project_id=project_id)

    existing_idem = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="project_member.add",
        idempotency_key=idempotency_key,
    )
    if existing_idem is not None:
        if existing_idem.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        ref = existing_idem.response_ref or {}
        return dict(ref)

    try:
        _check_expected_version(project, expected_project_version)

        target_user = await repo.get_org_user(
            session, organization_id=ctx.organization.id, user_id=user_id
        )
        if target_user is None or target_user.is_disabled:
            raise ValueError("validation")

        existing = await repo.get_project_member(
            session,
            organization_id=ctx.organization.id,
            project_id=project_id,
            user_id=user_id,
        )
        if existing is not None:
            raise ValueError("validation")

        member = await repo.create_project_member(
            session,
            organization_id=ctx.organization.id,
            project_id=project_id,
            user_id=user_id,
            role=role,
            created_by=ctx.user.id,
        )
        await repo.bump_project_version(session, project)
        payload = build_project_member_payload(
            project_id=project_id,
            user_id=user_id,
            role=member.role,
            display_name=target_user.display_name,
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=ctx.organization.id,
                actor_user_id=ctx.user.id,
                action="project_member.add",
                resource_type="project_member",
                resource_id=member.id,
                project_id=project_id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        await repo.create_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="project_member.add",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref=payload,
            created_by=ctx.user.id,
        )
        return payload
    except ValueError as exc:
        code = str(exc)
        if code in {"validation", "version_conflict", "state"}:
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=ctx.organization.id,
                    actor_user_id=ctx.user.id,
                    action="project_member.add",
                    resource_type="project",
                    resource_id=project_id,
                    project_id=project_id,
                    result="failed",
                    request_hash=request_hash,
                ),
            )
        raise


async def patch_project_member_role(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    expected_project_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    if role not in repo.PROJECT_ROLES:
        raise ValueError("validation")

    project, _caller = await _resolve_writable_project(session, ctx, project_id=project_id)

    existing_idem = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="project_member.patch_role",
        idempotency_key=idempotency_key,
    )
    if existing_idem is not None:
        if existing_idem.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return dict(existing_idem.response_ref or {})

    try:
        _check_expected_version(project, expected_project_version)

        member = await repo.get_project_member(
            session,
            organization_id=ctx.organization.id,
            project_id=project_id,
            user_id=user_id,
        )
        if member is None:
            raise ValueError("not_found")

        owner_count = await repo.count_owners(
            session, organization_id=ctx.organization.id, project_id=project_id
        )
        if is_last_owner_violation(
            current_role=member.role, target_role=role, owner_count=owner_count
        ):
            raise ValueError("state")

        target_user = await repo.get_org_user(
            session, organization_id=ctx.organization.id, user_id=user_id
        )
        await repo.update_project_member_role(session, member, role=role)
        await repo.bump_project_version(session, project)
        payload = build_project_member_payload(
            project_id=project_id,
            user_id=user_id,
            role=role,
            display_name=target_user.display_name if target_user else None,
        )
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=ctx.organization.id,
                actor_user_id=ctx.user.id,
                action="project_member.patch_role",
                resource_type="project_member",
                resource_id=member.id,
                project_id=project_id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        await repo.create_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="project_member.patch_role",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref=payload,
            created_by=ctx.user.id,
        )
        return payload
    except ValueError as exc:
        code = str(exc)
        if code in {"validation", "version_conflict", "state"}:
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=ctx.organization.id,
                    actor_user_id=ctx.user.id,
                    action="project_member.patch_role",
                    resource_type="project",
                    resource_id=project_id,
                    project_id=project_id,
                    result="failed",
                    request_hash=request_hash,
                ),
            )
        raise


async def remove_project_member(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    expected_project_version: int | None,
    idempotency_key: str,
    request_hash: str,
) -> None:
    project, _caller = await _resolve_writable_project(session, ctx, project_id=project_id)

    existing_idem = await repo.get_idempotency_record(
        session,
        organization_id=ctx.organization.id,
        command_type="project_member.remove",
        idempotency_key=idempotency_key,
    )
    if existing_idem is not None:
        if existing_idem.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        return

    try:
        _check_expected_version(project, expected_project_version)

        member = await repo.get_project_member(
            session,
            organization_id=ctx.organization.id,
            project_id=project_id,
            user_id=user_id,
        )
        if member is None:
            raise ValueError("not_found")

        owner_count = await repo.count_owners(
            session, organization_id=ctx.organization.id, project_id=project_id
        )
        if is_last_owner_violation(
            current_role=member.role, target_role=None, owner_count=owner_count
        ):
            raise ValueError("state")

        member_id = member.id
        await repo.delete_project_member(session, member)
        await repo.bump_project_version(session, project)
        await append_audit_event(
            session,
            AuditAppendInput(
                organization_id=ctx.organization.id,
                actor_user_id=ctx.user.id,
                action="project_member.remove",
                resource_type="project_member",
                resource_id=member_id,
                project_id=project_id,
                result="ok",
                request_hash=request_hash,
            ),
        )
        await repo.create_idempotency_record(
            session,
            organization_id=ctx.organization.id,
            command_type="project_member.remove",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response_ref={"removed": True},
            created_by=ctx.user.id,
        )
    except ValueError as exc:
        code = str(exc)
        if code in {"validation", "version_conflict", "state"}:
            await append_audit_event(
                session,
                AuditAppendInput(
                    organization_id=ctx.organization.id,
                    actor_user_id=ctx.user.id,
                    action="project_member.remove",
                    resource_type="project",
                    resource_id=project_id,
                    project_id=project_id,
                    result="failed",
                    request_hash=request_hash,
                ),
            )
        raise


COMMAND_TYPE_CAPABILITY_TIGHTEN = "organization.capability_tighten"
COMMAND_TYPE_SIEM_EXPORT_PUT = "organization.siem_export.put"
VALID_TIGHTEN_LEVELS = frozenset({"global", "ability", "module", "connector"})


def _build_tighten_response(
    org: Organization, *, level: str, identifier: str | None
) -> dict[str, Any]:
    controls = org.capability_controls
    effective_scope: dict[str, Any] = {"level": level}
    if identifier is not None:
        effective_scope["id"] = identifier
    banner_scope = controls.get("banner_scope")
    banner: dict[str, Any] = {"scope": banner_scope} if banner_scope is not None else {}
    return {
        "version": org.aggregate_version,
        "tightened": True,
        "effective_scope": effective_scope,
        "banner": banner,
        "capability_controls": controls,
    }


def _tighten_controls(
    controls: dict[str, Any], *, level: str, identifier: str | None
) -> dict[str, Any]:
    from copy import deepcopy

    updated = deepcopy(controls)
    for key, default in DEFAULT_CAPABILITY_CONTROLS.items():
        updated.setdefault(key, deepcopy(default) if isinstance(default, list) else default)

    if level == "global":
        updated["ai_global_tightened"] = True
        updated["banner_scope"] = "global"
    elif level == "ability" and identifier is not None:
        caps = [str(item) for item in updated.get("tightened_capabilities", [])]
        if identifier not in caps:
            caps.append(identifier)
        updated["tightened_capabilities"] = caps
        updated["banner_scope"] = identifier
    elif level == "module" and identifier is not None:
        mods = [str(item) for item in updated.get("tightened_modules", [])]
        if identifier not in mods:
            mods.append(identifier)
        updated["tightened_modules"] = mods
        updated["banner_scope"] = identifier
    elif level == "connector" and identifier is not None:
        conns = [str(item) for item in updated.get("tightened_connectors", [])]
        if identifier not in conns:
            conns.append(identifier)
        updated["tightened_connectors"] = conns
        updated["banner_scope"] = identifier

    return updated


def _parse_tighten_target(target: dict[str, Any]) -> tuple[str, str | None]:
    level = str(target.get("level", ""))
    if level not in VALID_TIGHTEN_LEVELS:
        raise ValueError("validation")
    identifier: str | None = None
    if level == "ability":
        raw = target.get("capability_id")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    elif level == "module":
        raw = target.get("module")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    elif level == "connector":
        raw = target.get("connector_id")
        if raw is None:
            raise ValueError("validation")
        identifier = str(raw)
    return level, identifier


async def tighten_capability_controls(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    expected_version: int,
    target: dict[str, Any],
    reason: str | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    from app.modules.identity_tenancy import query_port as identity_query

    allowed = await identity_query.caller_is_owner_or_admin(
        session, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if not allowed:
        raise ValueError("forbidden")

    org_id = ctx.organization.id
    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CAPABILITY_TIGHTEN,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    level, identifier = _parse_tighten_target(target)
    org = ctx.organization
    if org.aggregate_version != expected_version:
        raise ValueError("version_conflict")

    now = datetime.now(UTC)
    org.capability_controls = _tighten_controls(
        org.capability_controls, level=level, identifier=identifier
    )
    org.updated_at = now
    org.aggregate_version += 1
    await session.flush()

    response = _build_tighten_response(org, level=level, identifier=identifier)
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="organization.capability_tighten",
            resource_type="organization",
            resource_id=org.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_CAPABILITY_TIGHTEN,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
    )
    _ = reason
    return response


def _connector_write_kill_active(controls: dict[str, Any]) -> bool:
    if controls.get("ai_global_tightened") is True:
        return True
    connectors = controls.get("tightened_connectors")
    return isinstance(connectors, list) and len(connectors) > 0


async def put_siem_export_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    expected_version: int,
    enabled: bool,
    destination_connector_id: uuid.UUID | None,
    filter_payload: dict[str, Any] | None,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, Any]:
    from app.modules.identity_tenancy import query_port as identity_query

    allowed = await identity_query.caller_is_owner(
        session, organization_id=ctx.organization.id, user_id=ctx.user.id
    )
    if not allowed:
        raise ValueError("forbidden")

    org_id = ctx.organization.id
    existing = await repo.get_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_SIEM_EXPORT_PUT,
        idempotency_key=idempotency_key,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency_conflict")
        if existing.response_ref is not None:
            return existing.response_ref

    if enabled and destination_connector_id is None:
        raise ValueError("validation")
    if enabled and destination_connector_id is not None:
        raise ValueError("not_found")

    org = ctx.organization
    if enabled and _connector_write_kill_active(org.capability_controls):
        raise ValueError("policy_deny")
    if org.aggregate_version != expected_version:
        raise ValueError("version_conflict")

    now = datetime.now(UTC)
    export_payload: dict[str, Any] = {"enabled": enabled}
    if destination_connector_id is not None:
        export_payload["destination_connector_id"] = str(destination_connector_id)
    if filter_payload is not None:
        export_payload["filter"] = filter_payload
    org.siem_export = export_payload
    org.updated_at = now
    org.aggregate_version += 1
    await session.flush()

    response = {
        "enabled": enabled,
        "version": org.aggregate_version,
        "destination_connector_id": (
            str(destination_connector_id) if destination_connector_id is not None else None
        ),
        "credential_present": False,
    }
    await append_audit_event(
        session,
        AuditAppendInput(
            organization_id=org_id,
            actor_user_id=ctx.user.id,
            action="organization.siem_export.put",
            resource_type="organization",
            resource_id=org.id,
            result="ok",
            request_hash=request_hash,
        ),
    )
    await repo.create_idempotency_record(
        session,
        organization_id=org_id,
        command_type=COMMAND_TYPE_SIEM_EXPORT_PUT,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response,
        created_by=ctx.user.id,
    )
    return response


async def get_workbench_for_caller(
    session: AsyncSession,
    ctx: SessionContext,
    *,
    project_id: uuid.UUID | None,
) -> dict[str, Any]:
    org_id = ctx.organization.id
    caller_id = ctx.user.id
    memberships = await identity_query.list_user_project_memberships(
        session, organization_id=org_id, user_id=caller_id
    )
    if not memberships:
        raise ValueError("forbidden")

    visible_project_ids = [pid for pid, _ in memberships]
    if project_id is not None:
        if project_id not in visible_project_ids:
            raise ValueError("not_found")
        filter_project_ids = [project_id]
    else:
        filter_project_ids = visible_project_ids

    pending = await approval_query.list_workbench_pending_approvals(
        session,
        organization_id=org_id,
        caller_id=caller_id,
        project_ids=filter_project_ids,
        limit=WORKBENCH_LIST_LIMIT,
    )
    active_runs = await run_query.list_workbench_active_runs(
        session,
        organization_id=org_id,
        project_ids=filter_project_ids,
        limit=WORKBENCH_LIST_LIMIT,
    )
    from app.modules.quota_governance import query_port as quota_query

    quota = await quota_query.get_current_quota(session, organization_id=org_id)
    if quota is None:
        raise ValueError("not_found")

    return {
        "pending_approvals": pending,
        "active_runs": active_runs,
        "gate_anomalies": [],
        "quota": quota,
    }
