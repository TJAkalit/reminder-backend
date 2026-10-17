import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.domain import milestone
from src.domain.clock import get_zone, local_date, now_utc
from src.domain.enums import CheckStatus, OccurrenceStatus
from src.domain.streak import current_streak
from src.dto.checklist import Checklist, ChecklistItem, CheckResult
from src.model import HabitCheck, HabitMilestone, Occurrence, Routine, User
from src.service import progress
from src.service.errors import ChecklistClosedError, ForbiddenError, NotFoundError
from src.service.notifier import ChecklistNotifier

logger = logging.getLogger(__name__)

# Tapping a habit in the checklist cycles its status.
NEXT_STATUS = {
    CheckStatus.PENDING: CheckStatus.DONE,
    CheckStatus.DONE: CheckStatus.SKIPPED,
    CheckStatus.SKIPPED: CheckStatus.PENDING,
}


class ChecklistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load(self, occurrence_id: int) -> Occurrence:
        occurrence = await self.session.scalar(
            select(Occurrence)
            .where(Occurrence.id == occurrence_id)
            .options(
                joinedload(Occurrence.routine).joinedload(Routine.user),
                selectinload(Occurrence.checks).joinedload(HabitCheck.habit),
            )
            .execution_options(populate_existing=True)
        )
        if occurrence is None:
            raise NotFoundError(f"Occurrence {occurrence_id} not found")
        return occurrence

    async def _view(self, occurrence: Occurrence, now: datetime) -> Checklist:
        checks = sorted(occurrence.checks, key=lambda c: (c.habit.sort_order, c.habit.id))
        records = await progress.load_records(self.session, [c.habit_id for c in checks], now)
        routine = occurrence.routine
        return Checklist(
            occurrence_id=occurrence.id,
            chat_id=routine.user.telegram_chat_id,
            message_id=occurrence.telegram_message_id,
            routine_title=routine.title,
            routine_emoji=routine.emoji,
            local_date=occurrence.local_date,
            is_open=occurrence.is_open(now),
            items=[
                ChecklistItem(
                    habit_id=check.habit_id,
                    title=check.habit.title,
                    emoji=check.habit.emoji,
                    status=check.status,
                    current_streak=current_streak([r.outcome for r in records[check.habit_id]]),
                )
                for check in checks
            ],
        )

    async def build(self, occurrence_id: int, now: datetime | None = None) -> Checklist:
        return await self._view(await self._load(occurrence_id), now or now_utc())

    async def toggle(
        self, chat_id: int, occurrence_id: int, habit_id: int, now: datetime | None = None
    ) -> CheckResult:
        now = now or now_utc()
        occurrence = await self._load(occurrence_id)
        if occurrence.routine.user.telegram_chat_id != chat_id:
            raise ForbiddenError("This checklist belongs to another user")
        if not occurrence.is_open(now):
            raise ChecklistClosedError("The day is over")
        check = next((c for c in occurrence.checks if c.habit_id == habit_id), None)
        if check is None:
            raise NotFoundError(f"Habit {habit_id} is not in this checklist")

        check.status = NEXT_STATUS[check.status]
        check.checked_at = None if check.status is CheckStatus.PENDING else now
        await self.session.flush()

        reached: int | None = None
        if check.status is CheckStatus.DONE:
            reached = await self._record_milestones(habit_id, occurrence, now)
        await self.session.commit()
        return CheckResult(
            checklist=await self._view(occurrence, now),
            habit_title=check.habit.title,
            new_status=check.status,
            milestone=reached,
        )

    async def _record_milestones(
        self, habit_id: int, occurrence: Occurrence, now: datetime
    ) -> int | None:
        """Store every reached threshold; return the one hit exactly by this check."""
        records = (await progress.load_records(self.session, [habit_id], now))[habit_id]
        streak = current_streak([r.outcome for r in records])
        known = set(
            await self.session.scalars(
                select(HabitMilestone.threshold).where(HabitMilestone.habit_id == habit_id)
            )
        )
        for threshold in milestone.reached(streak):
            if threshold not in known:
                self.session.add(
                    HabitMilestone(
                        habit_id=habit_id, threshold=threshold, achieved_on=occurrence.local_date
                    )
                )
        return milestone.just_reached(streak)

    async def resend_today(
        self, user: User, notifier: ChecklistNotifier, now: datetime | None = None
    ) -> list[Checklist]:
        """Re-send today's open checklists (reviving ones the worker missed)."""
        now = now or now_utc()
        today = local_date(now, get_zone(user.timezone))
        occurrence_ids = list(
            await self.session.scalars(
                select(Occurrence.id)
                .join(Routine)
                .where(
                    Routine.user_id == user.id,
                    Occurrence.local_date == today,
                    Occurrence.status.in_([OccurrenceStatus.SENT, OccurrenceStatus.MISSED]),
                    Occurrence.closes_at > now,
                )
                .order_by(Routine.sort_order, Routine.id)
            )
        )
        sent: list[Checklist] = []
        for occurrence_id in occurrence_ids:
            occurrence = await self._load(occurrence_id)
            old_message_id = occurrence.telegram_message_id
            occurrence.status = OccurrenceStatus.SENT
            checklist = await self._view(occurrence, now)
            occurrence.telegram_message_id = await notifier.send_checklist(checklist)
            await self.session.commit()
            if old_message_id is not None:
                try:
                    await notifier.remove_buttons(checklist.chat_id, old_message_id)
                except Exception:
                    logger.warning("Could not detach message %s", old_message_id, exc_info=True)
            sent.append(checklist.model_copy(update={"message_id": occurrence.telegram_message_id}))
        return sent
