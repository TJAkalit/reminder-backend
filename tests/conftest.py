import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from src.db.base import Base
from src.db.session import create_engine, create_session_factory
from src.dto.checklist import Checklist
from src.model import Habit, Routine, User
from src.service.access import AccessService
from src.service.habit import HabitService
from src.service.routine import RoutineService
from src.service.user import UserService

# 2026-10-18 05:00 MSK
T0 = datetime(2026, 10, 18, 2, 0, tzinfo=UTC)


# Set TEST_DATABASE_URL=postgresql+asyncpg://... to run the suite on PostgreSQL.
# Each test then gets its own throwaway schema; other schemas are never touched.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    if TEST_DATABASE_URL is None:
        engine = create_engine("sqlite+aiosqlite://", poolclass=StaticPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()
        return

    schema = f"test_{uuid.uuid4().hex[:12]}"
    engine = create_engine(TEST_DATABASE_URL, schema=schema, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@dataclass
class FakeNotifier:
    sent: list[Checklist] = field(default_factory=list)
    updated: list[Checklist] = field(default_factory=list)
    closed: list[Checklist] = field(default_factory=list)
    detached: list[int] = field(default_factory=list)
    fail: bool = False
    _next_id: int = 100

    async def send_checklist(self, checklist: Checklist) -> int:
        if self.fail:
            raise RuntimeError("telegram is down")
        self.sent.append(checklist)
        self._next_id += 1
        return self._next_id

    async def update_checklist(self, checklist: Checklist) -> None:
        self.updated.append(checklist)

    async def close_checklist(self, checklist: Checklist) -> None:
        self.closed.append(checklist)

    async def remove_buttons(self, chat_id: int, message_id: int) -> None:
        self.detached.append(message_id)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@dataclass
class World:
    user: User
    routine: Routine
    habits: list[Habit]


@pytest.fixture
async def world(session: AsyncSession) -> World:
    """User in Moscow with «Утро» every day at 07:00 and two habits, created at T0."""
    await AccessService(session).allow(111, by_chat_id=None)
    user, _ = await UserService(session).register(111, "Tester", "Europe/Moscow")
    routine = await RoutineService(session).create(
        user, "Утро", "FREQ=DAILY;BYHOUR=7;BYMINUTE=0", emoji="🌅", now=T0
    )
    habits = [
        await HabitService(session).create(routine, "Стакан воды", emoji="💧"),
        await HabitService(session).create(routine, "Зарядка"),
    ]
    return World(user=user, routine=routine, habits=habits)
