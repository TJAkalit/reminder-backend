from datetime import date, datetime

from pydantic import Field

from src.dto.base import Dto


class ScheduleOut(Dto):
    rrule: str = Field(examples=["FREQ=DAILY;BYHOUR=7;BYMINUTE=0"])
    start: date
    time: str = Field(description="Local time of day, HH:MM", examples=["07:00"])
    description: str = Field(examples=["каждый день в 07:00"])


class RoutineRef(Dto):
    id: int
    title: str
    emoji: str | None
    schedule: ScheduleOut


class HabitBrief(Dto):
    id: int
    title: str
    emoji: str | None


class RoutineOut(Dto):
    id: int
    title: str
    emoji: str | None
    is_active: bool
    schedule: ScheduleOut
    next_run_at: datetime | None
    habits: list[HabitBrief]
