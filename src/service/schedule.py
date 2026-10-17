"""Glue between routine rows and the pure domain schedule."""

from src.domain.clock import get_zone
from src.domain.schedule import Schedule, describe_rrule
from src.dto.routine import ScheduleOut
from src.model import Routine


def routine_schedule(routine: Routine, timezone: str) -> Schedule:
    return Schedule(routine.schedule_rrule, routine.schedule_start, get_zone(timezone))


def schedule_out(routine: Routine, timezone: str) -> ScheduleOut:
    schedule = routine_schedule(routine, timezone)
    return ScheduleOut(
        rrule=routine.schedule_rrule,
        start=routine.schedule_start,
        time=schedule.time_of_day.strftime("%H:%M"),
        description=describe_rrule(routine.schedule_rrule),
    )
