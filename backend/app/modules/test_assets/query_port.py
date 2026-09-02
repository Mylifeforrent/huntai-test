"""Cross-module read-only queries for test_assets (no ORM export to consumers)."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.test_assets import repository as repo


async def get_import_source_content(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    import_source_id: uuid.UUID,
    project_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_import_source(
        session,
        organization_id=organization_id,
        source_id=import_source_id,
    )
    if row is None or row.project_id != project_id:
        return None
    return {
        "id": row.id,
        "source_type": row.source_type,
        "project_id": row.project_id,
        "content_text": row.content_text,
        "data_classification": row.data_classification,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "created_at": row.created_at,
    }


async def get_import_source_metadata(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    import_source_id: uuid.UUID,
) -> dict[str, Any] | None:
    row = await repo.get_import_source(
        session,
        organization_id=organization_id,
        source_id=import_source_id,
    )
    if row is None:
        return None
    return {
        "id": row.id,
        "source_type": row.source_type,
        "project_id": row.project_id,
        "original_filename": row.original_filename,
        "byte_size": row.byte_size,
        "checksum": row.checksum,
        "data_classification": row.data_classification,
        "created_at": row.created_at,
    }
