from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.domain.clock import get_zone, local_date, now_utc
from src.dto.habit import HabitDayOut, HabitHistoryOut, HabitOut
from src.dto.routine import RoutineRef
from src.model import Habit, Routine, User
from src.service import progress
from src.service.errors import NotFoundError, ValidationError
from src.service.schedule import schedule_out

DEFAULT_HISTORY_DAYS = 365
MAX_HISTORY_DAYS = 3 * 366


class HabitService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _habits(self, user: User, *, include_archived: bool) -> list[Habit]:
        query = (
            select(Habit)
            .join(Routine)
            .where(Routine.user_id == user.id)
            .options(joinedload(Habit.routine))
            .order_by(Routine.sort_order, Routine.id, Habit.sort_order, Habit.id)
        )
        if not include_archived:
            query = query.where(Habit.archived_at.is_(None))
        return list(await self.session.scalars(query))

    async def list_active(self, user: User) -> list[Habit]:
        return await self._habits(user, include_archived=False)

    async def get_owned(self, user: User, habit_id: int) -> Habit:
        habit = await self.session.scalar(
            select(Habit)
            .join(Routine)
            .where(Habit.id == habit_id, Routine.user_id == user.id)
            .options(joinedload(Habit.routine))
        )
        if habit is None:
            raise NotFoundError(f"Habit {habit_id} not found")
        return habit

    async def _to_out(self, user: User, habits: list[Habit], now: datetime) -> list[HabitOut]:
        ids = [h.id for h in habits]
        records = await progress.load_records(self.session, ids, now)
        milestones = await progress.load_milestones(self.session, ids)
        today = local_date(now, get_zone(user.timezone))
        return [
            HabitOut(
                id=habit.id,
                title=habit.title,
                description=habit.description,
                emoji=habit.emoji,
                created_at=habit.created_at,
                archived_at=habit.archived_at,
                routine=RoutineRef(
                    id=habit.routine.id,
                    title=habit.routine.title,
                    emoji=habit.routine.emoji,
                    schedule=schedule_out(habit.routine, user.timezone),
                ),
                stats=progress.stats_out(
                    progress.stats(records[habit.id], today), milestones[habit.id]
                ),
            )
            for habit in habits
        ]

    async def list_out(
        self, user: User, *, include_archived: bool = False, now: datetime | None = None
    ) -> list[HabitOut]:
        habits = await self._habits(user, include_archived=include_archived)
        return await self._to_out(user, habits, now or now_utc())

    async def get_out(self, user: User, habit_id: int, now: datetime | None = None) -> HabitOut:
        habit = await self.get_owned(user, habit_id)
        (out,) = await self._to_out(user, [habit], now or now_utc())
        return out

    async def history(
        self,
        user: User,
        habit_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        now: datetime | None = None,
    ) -> HabitHistoryOut:
        now = now or now_utc()
        await self.get_owned(user, habit_id)
        date_to = date_to or local_date(now, get_zone(user.timezone))
        date_from = date_from or date_to - timedelta(days=DEFAULT_HISTORY_DAYS - 1)
        if date_from > date_to:
            raise ValidationError("date_from must not be after date_to")
        if (date_to - date_from).days >= MAX_HISTORY_DAYS:
            raise ValidationError(f"History range is limited to {MAX_HISTORY_DAYS} days")
        records = (await progress.load_records(self.session, [habit_id], now))[habit_id]
        return HabitHistoryOut(
            habit_id=habit_id,
            date_from=date_from,
            date_to=date_to,
            days=[
                HabitDayOut(date=r.day, outcome=r.outcome)
                for r in records
                if date_from <= r.day <= date_to
            ],
        )

    async def create(
        self,
        routine: Routine,
        title: str,
        *,
        emoji: str | None = None,
        description: str | None = None,
    ) -> Habit:
        """New habits join the routine's checklist starting from its next run."""
        title = title.strip()
        if not title:
            raise ValidationError("Habit title must not be empty")
        max_order = await self.session.scalar(
            select(func.max(Habit.sort_order)).where(Habit.routine_id == routine.id)
        )
        habit = Habit(
            routine_id=routine.id,
            title=title,
            emoji=emoji,
            description=description,
            sort_order=(max_order or 0) + 1,
        )
        self.session.add(habit)
        await self.session.commit()
        return habit

    async def archive(self, user: User, habit_id: int, now: datetime | None = None) -> Habit:
        habit = await self.get_owned(user, habit_id)
        if habit.archived_at is None:
            habit.archived_at = now or now_utc()
            await self.session.commit()
        return habit
