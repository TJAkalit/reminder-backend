from datetime import date, datetime
from enum import StrEnum

from src.domain.enums import CheckStatus
from src.dto.base import Dto


class TodayState(StrEnum):
    # The run is later today.
    UPCOMING = "upcoming"
    # The checklist was sent and can still be checked.
    OPEN = "open"
    # The run time has passed but the worker has not created the checklist (yet).
    NOT_SENT = "not_sent"
    # The worker missed the run (it was down past the grace period).
    MISSED = "missed"


class TodayItemOut(Dto):
    habit_id: int
    title: str
    emoji: str | None
    status: CheckStatus
    current_streak: int


class TodayRoutineOut(Dto):
    routine_id: int
    title: str
    emoji: str | None
    schedule_description: str
    scheduled_at: datetime | None
    occurrence_id: int | None
    state: TodayState
    items: list[TodayItemOut]


class TodayOut(Dto):
    date: date
    timezone: str
    routines: list[TodayRoutineOut]
