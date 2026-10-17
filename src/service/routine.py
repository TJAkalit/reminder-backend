from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from src.domain.clock import get_zone, local_date, now_utc
from src.domain.schedule import InvalidScheduleError, normalize_rrule
from src.dto.routine import HabitBrief, RoutineOut
from src.model import Habit, Routine, User
from src.service.errors import NotFoundError, ValidationError
from src.service.schedule import routine_schedule, schedule_out


def _active_habits(routine: Routine) -> list[Habit]:
    return [habit for habit in routine.habits if not habit.is_archived]


class RoutineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_routines(self, user: User, *, active_only: bool = True) -> list[Routine]:
        """User's routines with their non-archived habits loaded."""
        query = (
            select(Routine)
            .where(Routine.user_id == user.id)
            .options(
                selectinload(Routine.habits),
                with_loader_criteria(Habit, Habit.archived_at.is_(None)),
            )
            .order_by(Routine.sort_order, Routine.id)
        )
        if active_only:
            query = query.where(Routine.is_active.is_(True))
        return list(await self.session.scalars(query))

    async def list_out(self, user: User) -> list[RoutineOut]:
        routines = await self.list_routines(user, active_only=False)
        return [
            RoutineOut(
                id=routine.id,
                title=routine.title,
                emoji=routine.emoji,
                is_active=routine.is_active,
                schedule=schedule_out(routine, user.timezone),
                next_run_at=routine.next_run_at,
                habits=[HabitBrief.model_validate(h) for h in _active_habits(routine)],
            )
            for routine in routines
        ]

    async def get_owned(self, user: User, routine_id: int) -> Routine:
        routine = await self.session.get(Routine, routine_id)
        if routine is None or routine.user_id != user.id:
            raise NotFoundError(f"Routine {routine_id} not found")
        return routine

    async def create(
        self,
        user: User,
        title: str,
        rrule: str,
        *,
        emoji: str | None = None,
        now: datetime | None = None,
    ) -> Routine:
        now = now or now_utc()
        title = title.strip()
        if not title:
            raise ValidationError("Routine title must not be empty")
        try:
            rrule = normalize_rrule(rrule)
        except InvalidScheduleError as exc:
            raise ValidationError(str(exc)) from exc
        max_order = await self.session.scalar(
            select(func.max(Routine.sort_order)).where(Routine.user_id == user.id)
        )
        routine = Routine(
            user_id=user.id,
            title=title,
            emoji=emoji,
            schedule_rrule=rrule,
            schedule_start=local_date(now, get_zone(user.timezone)),
            sort_order=(max_order or 0) + 1,
        )
        routine.next_run_at = routine_schedule(routine, user.timezone).next_after(now)
        self.session.add(routine)
        await self.session.commit()
        return routine
