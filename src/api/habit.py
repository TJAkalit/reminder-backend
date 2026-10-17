from datetime import date

from fastapi import APIRouter

from src.api.deps import CurrentUser, SessionDep
from src.dto.habit import HabitHistoryOut, HabitOut
from src.service.habit import HabitService

router = APIRouter(prefix="/habits", tags=["habits"])


@router.get("")
async def list_habits(
    session: SessionDep, user: CurrentUser, include_archived: bool = False
) -> list[HabitOut]:
    return await HabitService(session).list_out(user, include_archived=include_archived)


@router.get("/{habit_id}")
async def get_habit(habit_id: int, session: SessionDep, user: CurrentUser) -> HabitOut:
    return await HabitService(session).get_out(user, habit_id)


@router.get("/{habit_id}/history")
async def get_habit_history(
    habit_id: int,
    session: SessionDep,
    user: CurrentUser,
    date_from: date | None = None,
    date_to: date | None = None,
) -> HabitHistoryOut:
    """Day outcomes for a heatmap. Defaults to the last 365 days."""
    return await HabitService(session).history(user, habit_id, date_from, date_to)
