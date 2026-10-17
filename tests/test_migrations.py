from pathlib import Path

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
