import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity_tenancy.models import (
    AuthSession,
    CommandIdempotencyRecord,
    OidcLoginDraft,
    Organization,
    Project,
    ProjectMember,
    User,
)


@dataclass(frozen=True)
class MembershipRow:
    project_id: uuid.UUID
    project_name: str
    role: str


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode("ascii")).digest()
    import base64

    code_challenge = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")
    return verifier, code_challenge


async def create_oidc_draft(
    session: AsyncSession,
    *,
    state: str,
    nonce: str,
    code_verifier: str,
    return_path: str | None,
    expires_at: datetime,
) -> OidcLoginDraft:
    draft = OidcLoginDraft(
        id=uuid.uuid4(),
        state=state,
        nonce=nonce,
        code_verifier=code_verifier,
        return_path=return_path,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
        consumed_at=None,
    )
    session.add(draft)
    await session.flush()
    return draft


async def get_oidc_draft_by_state(session: AsyncSession, state: str) -> OidcLoginDraft | None:
    result = await session.execute(select(OidcLoginDraft).where(OidcLoginDraft.state == state))
    return result.scalar_one_or_none()


async def consume_oidc_draft(session: AsyncSession, draft: OidcLoginDraft) -> None:
    draft.consumed_at = datetime.now(UTC)
    await session.flush()


async def find_users_by_idp_subject(session: AsyncSession, idp_subject: str) -> list[User]:
    result = await session.execute(select(User).where(User.idp_subject == idp_subject))
    return list(result.scalars().all())


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_organization_by_id(
    session: AsyncSession, organization_id: uuid.UUID
) -> Organization | None:
    result = await session.execute(select(Organization).where(Organization.id == organization_id))
    return result.scalar_one_or_none()


async def create_auth_session(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
    last_reauth_at: datetime | None = None,
) -> AuthSession:
    auth_session = AuthSession(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_id=user_id,
        created_at=datetime.now(UTC),
        expires_at=expires_at,
        revoked_at=None,
        last_reauth_at=last_reauth_at,
    )
    session.add(auth_session)
    await session.flush()
    return auth_session


async def get_auth_session_by_id(
    session: AsyncSession, session_id: uuid.UUID
) -> AuthSession | None:
    result = await session.execute(select(AuthSession).where(AuthSession.id == session_id))
    return result.scalar_one_or_none()


async def revoke_auth_session(session: AsyncSession, auth_session: AuthSession) -> None:
    if auth_session.revoked_at is None:
        auth_session.revoked_at = datetime.now(UTC)
        await session.flush()


async def count_project_memberships(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ProjectMember)
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
        )
    )
    return int(result.scalar_one())


async def list_memberships(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> list[MembershipRow]:
    result = await session.execute(
        select(ProjectMember, Project)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.user_id == user_id,
        )
    )
    rows: list[MembershipRow] = []
    for member, project in result.all():
        rows.append(
            MembershipRow(
                project_id=member.project_id,
                project_name=project.name,
                role=member.role,
            )
        )
    return rows


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
) -> CommandIdempotencyRecord:
    record = CommandIdempotencyRecord(
        id=uuid.uuid4(),
        organization_id=organization_id,
        command_type=command_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_ref=response_ref,
        created_at=datetime.now(UTC),
        created_by=created_by,
    )
    session.add(record)
    await session.flush()
    return record
