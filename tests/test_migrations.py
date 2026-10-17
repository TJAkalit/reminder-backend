import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def test_migrations_apply_and_match_models(tmp_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    config.attributes["configure_logger"] = False

    command.upgrade(config, "head")
    # Fails if the models have changes that are not covered by a migration.
    command.check(config)
    command.downgrade(config, "base")


def test_existing_users_keep_access(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "legacy.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")
    config.attributes["configure_logger"] = False

    command.upgrade(config, "98485763aaf0")  # before chat_access
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO users (telegram_chat_id, display_name, timezone, created_at)"
            " VALUES (416, 'Owner', 'Europe/Moscow', '2026-10-18 00:00:00')"
        )
    command.upgrade(config, "head")
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT telegram_chat_id, status, is_admin FROM chat_access").fetchall()
    assert rows == [(416, "allowed", 0)]


@pytest.mark.skipif("TEST_DATABASE_URL" not in os.environ, reason="PostgreSQL not configured")
def test_migrations_on_postgres() -> None:
    import asyncio

    from sqlalchemy import text

    from src.db.session import create_engine

    url = os.environ["TEST_DATABASE_URL"]
    schema = f"test_{uuid.uuid4().hex[:12]}"
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    config.attributes["schema"] = schema
    try:
        command.upgrade(config, "head")  # also creates the schema
        command.check(config)
        command.downgrade(config, "base")
    finally:

        async def drop() -> None:
            engine = create_engine(url)
            async with engine.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await engine.dispose()

        asyncio.run(drop())
