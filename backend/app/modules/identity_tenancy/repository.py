import base64
import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, func, or_, select
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

PROJECT_ROLES = frozenset({"owner", "admin", "tester", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin"})


@dataclass(frozen=True)
class MembershipRow:
    project_id: uuid.UUID
    project_name: str
    role: str


@dataclass(frozen=True)
class ProjectListRow:
    project: Project
    my_role: str


@dataclass(frozen=True)
class MemberListRow:
    member: ProjectMember
    display_name: str | None
    email: str | None


def hash_request_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = hashlib.sha256(verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")
    return verifier, code_challenge


def escape_like_metacharacters(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_name_id_cursor(*, name: str, item_id: uuid.UUID) -> str:
    payload = json.dumps({"n": name, "i": str(item_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_name_id_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        name = data["n"]
        item_id = uuid.UUID(data["i"])
        if not isinstance(name, str):
            raise ValueError("invalid_cursor")
        return name, item_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


def encode_uuid_cursor(item_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(item_id).encode("utf-8")).decode("ascii")


def decode_uuid_cursor(cursor: str) -> uuid.UUID:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        return uuid.UUID(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid_cursor") from exc


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


async def get_org_user(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    result = await session.execute(
        select(User).where(User.organization_id == organization_id, User.id == user_id)
    )
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


async def get_project(
    session: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID
) -> Project | None:
    result = await session.execute(
        select(Project).where(
            Project.organization_id == organization_id,
            Project.id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def get_project_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ProjectMember | None:
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def count_owners(
    session: AsyncSession, *, organization_id: uuid.UUID, project_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ProjectMember)
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.project_id == project_id,
            ProjectMember.role == "owner",
        )
    )
    return int(result.scalar_one())


async def list_member_projects(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    q: str | None,
    cursor_name: str | None,
    cursor_id: uuid.UUID | None,
    fetch_limit: int | None,
) -> list[ProjectListRow]:
    stmt = (
        select(Project, ProjectMember.role)
        .join(
            ProjectMember,
            and_(
                ProjectMember.project_id == Project.id,
                ProjectMember.organization_id == Project.organization_id,
            ),
        )
        .where(
            Project.organization_id == organization_id,
            ProjectMember.user_id == user_id,
        )
    )
    if q:
        pattern = f"%{escape_like_metacharacters(q)}%"
        stmt = stmt.where(
            or_(
                Project.name.ilike(pattern, escape="\\"),
                Project.jira_project_key.ilike(pattern, escape="\\"),
            )
        )
    if cursor_name is not None and cursor_id is not None:
        stmt = stmt.where(
            or_(
                Project.name > cursor_name,
                and_(Project.name == cursor_name, Project.id > cursor_id),
            )
        )
    stmt = stmt.order_by(Project.name, Project.id)
    if fetch_limit is not None:
        stmt = stmt.limit(fetch_limit)
    result = await session.execute(stmt)
    return [ProjectListRow(project=project, my_role=role) for project, role in result.all()]


async def list_project_members(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    role: str | None,
    cursor_id: uuid.UUID | None,
    fetch_limit: int | None,
) -> list[MemberListRow]:
    stmt = (
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(
            ProjectMember.organization_id == organization_id,
            ProjectMember.project_id == project_id,
        )
    )
    if role is not None:
        stmt = stmt.where(ProjectMember.role == role)
    if cursor_id is not None:
        stmt = stmt.where(ProjectMember.user_id > cursor_id)
    stmt = stmt.order_by(ProjectMember.user_id)
    if fetch_limit is not None:
        stmt = stmt.limit(fetch_limit)
    result = await session.execute(stmt)
    rows: list[MemberListRow] = []
    for member, user in result.all():
        rows.append(
            MemberListRow(
                member=member,
                display_name=user.display_name,
                email=user.email,
            )
        )
    return rows


async def create_project_member(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    created_by: uuid.UUID,
) -> ProjectMember:
    now = datetime.now(UTC)
    member = ProjectMember(
        id=uuid.uuid4(),
        organization_id=organization_id,
        created_at=now,
        updated_at=now,
        created_by=created_by,
        aggregate_version=1,
        project_id=project_id,
        user_id=user_id,
        role=role,
    )
    session.add(member)
    await session.flush()
    return member


async def update_project_member_role(
    session: AsyncSession, member: ProjectMember, *, role: str
) -> ProjectMember:
    member.role = role
    member.updated_at = datetime.now(UTC)
    member.aggregate_version += 1
    await session.flush()
    return member


async def delete_project_member(session: AsyncSession, member: ProjectMember) -> None:
    await session.execute(delete(ProjectMember).where(ProjectMember.id == member.id))
    await session.flush()


async def bump_project_version(session: AsyncSession, project: Project) -> Project:
    project.aggregate_version += 1
    project.updated_at = datetime.now(UTC)
    await session.flush()
    return project


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
