from datetime import date, datetime

from pydantic import Field

from src.domain.enums import DayOutcome
from src.dto.base import Dto
from src.dto.routine import RoutineRef


class MilestoneOut(Dto):
    threshold: int
    achieved_on: date


class NextMilestoneOut(Dto):
    threshold: int
    remaining: int


class HabitStatsOut(Dto):
    current_streak: int
    best_streak: int
    completion_rate_30d: float | None = Field(
        description="Share of done days over the last 30 days; null if nothing counted yet"
    )
    milestones: list[MilestoneOut]
    next_milestone: NextMilestoneOut | None


class HabitOut(Dto):
    id: int
    title: str
    description: str | None
    emoji: str | None
    created_at: datetime
    archived_at: datetime | None
    routine: RoutineRef
    stats: HabitStatsOut


class HabitDayOut(Dto):
    date: date
    outcome: DayOutcome


class HabitHistoryOut(Dto):
    habit_id: int
    date_from: date
    date_to: date
    days: list[HabitDayOut]
