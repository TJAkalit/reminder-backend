from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domain.clock import get_zone, local_date, now_utc
from src.domain.enums import CheckStatus, OccurrenceStatus
from src.domain.schedule import describe_rrule
from src.domain.streak import current_streak
from src.dto.today import TodayItemOut, TodayOut, TodayRoutineOut, TodayState
from src.model import HabitCheck, Occurrence, User
from src.service import progress
from src.service.routine import RoutineService
from src.service.schedule import routine_schedule


class TodayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user: User, now: datetime | None = None) -> TodayOut:
        now = now or now_utc()
        tz = get_zone(user.timezone)
        today = local_date(now, tz)
        routines = await RoutineService(self.session).list_routines(user)

        occurrences = {
            occ.routine_id: occ
            for occ in await self.session.scalars(
                select(Occurrence)
                .where(
                    Occurrence.routine_id.in_([r.id for r in routines]),
                    Occurrence.local_date == today,
                )
                .options(selectinload(Occurrence.checks).joinedload(HabitCheck.habit))
                .order_by(Occurrence.scheduled_for)
            )
        }
        habit_ids = {h.id for r in routines for h in r.habits}
        habit_ids |= {c.habit_id for occ in occurrences.values() for c in occ.checks}
        records = await progress.load_records(self.session, habit_ids, now)

        def streak(habit_id: int) -> int:
            return current_streak([r.outcome for r in records[habit_id]])

        result: list[TodayRoutineOut] = []
        for routine in routines:
            occurrence = occurrences.get(routine.id)
            runs = routine_schedule(routine, user.timezone).runs_on(today)
            if occurrence is None and not runs:
                continue
            if occurrence is not None:
                state = (
                    TodayState.MISSED
                    if occurrence.status is OccurrenceStatus.MISSED
                    else TodayState.OPEN
                )
                checks = sorted(occurrence.checks, key=lambda c: (c.habit.sort_order, c.habit.id))
                items = [
                    TodayItemOut(
                        habit_id=c.habit_id,
                        title=c.habit.title,
                        emoji=c.habit.emoji,
                        status=c.status,
                        current_streak=streak(c.habit_id),
                    )
                    for c in checks
                ]
                scheduled_at = occurrence.scheduled_for
            else:
                scheduled_at = runs[0]
                state = TodayState.UPCOMING if scheduled_at > now else TodayState.NOT_SENT
                items = [
                    TodayItemOut(
                        habit_id=h.id,
                        title=h.title,
                        emoji=h.emoji,
                        status=CheckStatus.PENDING,
                        current_streak=streak(h.id),
                    )
                    for h in routine.habits
                ]
            result.append(
                TodayRoutineOut(
                    routine_id=routine.id,
                    title=routine.title,
                    emoji=routine.emoji,
                    schedule_description=describe_rrule(routine.schedule_rrule),
                    scheduled_at=scheduled_at,
                    occurrence_id=occurrence.id if occurrence else None,
                    state=state,
                    items=items,
                )
            )
        return TodayOut(date=today, timezone=user.timezone, routines=result)
