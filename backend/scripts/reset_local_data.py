"""Dev-only: wipe local business data and re-seed identity.

Resets the local database back to the state `scripts/seed_local_identity.py`
alone produces, so the tutorials can be replayed from scratch:

    cd backend && uv run python scripts/reset_local_data.py --yes

Truncates every table in the schemas this app owns (discovered from the
database, so newly added tables are covered automatically), leaves `public`
(where `alembic_version` lives) and all schema structure untouched, then re-runs
the identity seed. TRUNCATE is not DDL, so a running backend does not need a
restart. Local development only.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import dispose_engine, get_engine

# Schemas this app owns, hard-coded on purpose: enumerating "every schema except
# public" would also reach pg_catalog / information_schema.
APP_SCHEMAS: tuple[str, ...] = (
    "ai_governance",
    "approval_policy",
    "execution_registry",
    "identity_tenancy",
    "integration_hub",
    "quality_gates",
    "quota_governance",
    "release_orchestration",
    "results_evidence",
    "run_orchestration",
    "test_assets",
)


async def list_app_tables() -> list[str]:
    """Fully qualified, quoted table names currently present in this app's schemas."""
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT schemaname, tablename FROM pg_tables "
                "WHERE schemaname = ANY(:schemas) ORDER BY schemaname, tablename"
            ),
            {"schemas": list(APP_SCHEMAS)},
        )
        return [f'"{schema}"."{name}"' for schema, name in result.all()]


async def truncate(tables: list[str]) -> None:
    """One atomic statement, so a failure part-way cannot leave a half-empty database."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} CASCADE"))


def load_seed_module() -> ModuleType:
    """Load `seed_local_identity.py` by path, the same way tests/conftest.py does."""
    seed_path = Path(__file__).resolve().parent / "seed_local_identity.py"
    spec = importlib.util.spec_from_file_location("seed_local_identity", seed_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {seed_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema_summary(tables: list[str]) -> str:
    per_schema: dict[str, int] = {}
    for qualified in tables:
        schema = qualified.split('"')[1]
        per_schema[schema] = per_schema.get(schema, 0) + 1
    return ", ".join(f"{name} ({count})" for name, count in sorted(per_schema.items()))


async def run(confirmed: bool) -> int:
    try:
        tables = await list_app_tables()
        if not tables:
            print("no tables found in this app's schemas; run `uv run alembic upgrade head` first")
            return 1

        print(f"will truncate {len(tables)} tables: {schema_summary(tables)}")
        if not confirmed:
            print("nothing was changed. re-run with --yes to wipe and re-seed.")
            return 2

        await truncate(tables)
        print(f"truncated {len(tables)} tables (schema structure and alembic_version untouched)")

        module = load_seed_module()
        await module.seed()
        print("done. the backend does not need a restart; refresh the browser to start over.")
        return 0
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="actually wipe data and re-seed (without it, only prints what would go)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.app_env == "production":
        print(f"refusing to run with APP_ENV={settings.app_env!r}: local development only")
        raise SystemExit(2)

    raise SystemExit(asyncio.run(run(args.yes)))


if __name__ == "__main__":
    main()
