import re
from typing import Any

from sqlalchemy import event, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # API and worker are separate processes writing to the same file.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def is_postgres(url: str) -> bool:
    return make_url(url).get_backend_name() == "postgresql"


def checked_schema(schema: str) -> str:
    """Schema names end up in SQL (CREATE SCHEMA), so only plain identifiers are allowed."""
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"Invalid PostgreSQL schema name: {schema!r}")
    return schema


def postgres_connect_args(schema: str | None) -> dict[str, Any]:
    """Every connection works inside ``schema`` (tables and alembic_version live there)."""
    if not schema:
        return {}
    return {"server_settings": {"search_path": checked_schema(schema)}}


def create_engine(
    url: str | None = None, *, schema: str | None = None, **kwargs: Any
) -> AsyncEngine:
    """Engine for the app. ``schema`` defaults to DATABASE_SCHEMA and applies to PostgreSQL only."""
    settings = get_settings()
    url = url or settings.database_url
    if is_postgres(url):
        kwargs.setdefault("connect_args", postgres_connect_args(schema or settings.database_schema))
        kwargs.setdefault("pool_pre_ping", True)
        if "poolclass" not in kwargs:
            # API and worker each keep a small pool; the role's connection limit is shared.
            kwargs.setdefault("pool_size", 5)
            kwargs.setdefault("max_overflow", 5)
    engine = create_async_engine(url, echo=settings.database_echo, **kwargs)
    if engine.dialect.name == "sqlite":
        event.listen(engine.sync_engine, "connect", _sqlite_pragmas)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
