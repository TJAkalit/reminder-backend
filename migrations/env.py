import asyncio
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import src.model  # noqa: F401  (registers all tables on Base.metadata)
from src.config import get_settings
from src.db.base import Base, UTCDateTime
from src.db.session import checked_schema, is_postgres, postgres_connect_args

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _render_item(type_: str, obj: object, autogen_context: object) -> str | Literal[False]:
    # Migrations must not depend on application code: UTCDateTime is a plain timestamptz.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        # SQLite cannot ALTER most things; batch mode recreates tables. Harmless on PostgreSQL.
        render_as_batch=True,
        compare_type=True,
        render_item=_render_item,
        **kwargs,  # type: ignore[arg-type]
    )


def run_migrations_offline() -> None:
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


def _schema() -> str | None:
    schema = config.attributes.get("schema", get_settings().database_schema)
    return checked_schema(schema) if schema else None


async def run_async_migrations() -> None:
    url, schema = _url(), _schema()
    # Not src.db.session.create_engine: SQLite PRAGMA foreign_keys=ON breaks batch-mode table
    # rebuilds (ON DELETE CASCADE would wipe child rows).
    connect_args = postgres_connect_args(schema) if is_postgres(url) else {}
    engine = create_async_engine(url, poolclass=pool.NullPool, connect_args=connect_args)
    async with engine.connect() as connection:
        if connect_args and schema:
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await connection.commit()
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
