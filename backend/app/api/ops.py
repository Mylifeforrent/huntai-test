"""Operational probes for container orchestration (Stage 12).

These are NOT product APIs: they live outside ``/api/v1``, carry no API number and
require no session. ``/healthz`` answers "is the process serving?" and
``/readyz`` answers "can it reach its database?". Neither may reveal internals
(DSN, driver text, stack traces) because they are unauthenticated.
"""

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.db import get_engine

ops_router = APIRouter()


@ops_router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up and serving. Deliberately does not touch the DB."""
    return {"status": "ok"}


@ops_router.get("/readyz")
async def readyz(response: Response) -> dict[str, str]:
    """Readiness: the database is reachable.

    Returns 503 with a fixed, non-descriptive body when the check fails so the
    probe cannot be used to probe infrastructure details.
    """
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any failure means "not ready"; detail stays server-side
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}
