from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.app import create_app
from tests.conftest import World


@pytest.fixture
async def client(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app(session_factory)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


def as_user(world: World) -> dict[str, str]:
    return {"X-User-Id": str(world.user.id)}


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_users(client: AsyncClient, world: World) -> None:
    response = await client.get("/api/v1/users")
    assert response.json() == [
        {"id": world.user.id, "display_name": "Tester", "timezone": "Europe/Moscow"}
    ]


async def test_user_header_required(client: AsyncClient, world: World) -> None:
    assert (await client.get("/api/v1/habits")).status_code == 401
    assert (await client.get("/api/v1/habits", headers={"X-User-Id": "999"})).status_code == 401


async def test_routines(client: AsyncClient, world: World) -> None:
    response = await client.get("/api/v1/routines", headers=as_user(world))
    assert response.status_code == 200
    (routine,) = response.json()
    assert routine["title"] == "Утро"
    assert routine["schedule"]["description"] == "каждый день в 07:00"
    assert routine["schedule"]["time"] == "07:00"
    assert [h["title"] for h in routine["habits"]] == ["Стакан воды", "Зарядка"]


async def test_habits(client: AsyncClient, world: World) -> None:
    response = await client.get("/api/v1/habits", headers=as_user(world))
    habits = response.json()
    assert len(habits) == 2
    assert habits[0]["stats"] == {
        "current_streak": 0,
        "best_streak": 0,
        "completion_rate_30d": None,
        "milestones": [],
        "next_milestone": {"threshold": 7, "remaining": 7},
    }
    habit_id = habits[0]["id"]
    detail = await client.get(f"/api/v1/habits/{habit_id}", headers=as_user(world))
    assert detail.json()["routine"]["title"] == "Утро"
    history = await client.get(f"/api/v1/habits/{habit_id}/history", headers=as_user(world))
    assert history.status_code == 200
    assert history.json()["days"] == []


async def test_habit_not_found(client: AsyncClient, world: World) -> None:
    response = await client.get("/api/v1/habits/999", headers=as_user(world))
    assert response.status_code == 404


async def test_history_validates_range(client: AsyncClient, world: World) -> None:
    habit_id = world.habits[0].id
    response = await client.get(
        f"/api/v1/habits/{habit_id}/history",
        params={"date_from": "2026-10-10", "date_to": "2026-10-01"},
        headers=as_user(world),
    )
    assert response.status_code == 422


async def test_today(client: AsyncClient, world: World) -> None:
    response = await client.get("/api/v1/today", headers=as_user(world))
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Europe/Moscow"
    assert len(body["routines"]) == 1
