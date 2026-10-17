"""The worker's tick: create due checklists, send them and close finished days (D-006, D-018)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, with_loader_criteria

from src.domain.clock import day_end_utc, get_zone, local_date
from src.domain.enums import AccessStatus, OccurrenceStatus
from src.model import ChatAccess, Habit, HabitCheck, Occurrence, Routine, User
from src.service.checklist import ChecklistService
from src.service.notifier import ChecklistNotifier
from src.service.schedule import routine_schedule

logger = logging.getLogger(__name__)

# Safety net for very long downtimes: never create more than this many runs per routine per tick.
MAX_CATCH_UP_RUNS = 400


@dataclass
class TickReport:
    sent: int = 0
    missed: int = 0
    closed: int = 0
    failed: int = 0


class SchedulerService:
    def __init__(
        self, session: AsyncSession, notifier: ChecklistNotifier, grace: timedelta
    ) -> None:
        self.session = session
        self.notifier = notifier
        self.grace = grace
        self.checklists = ChecklistService(session)

    async def tick(self, now: datetime) -> TickReport:
        report = TickReport()
        routines = list(
            await self.session.scalars(
                select(Routine)
                .join(User)
                # Revoked chats get nothing; their runs are caught up as missed if re-allowed.
                .join(ChatAccess, ChatAccess.telegram_chat_id == User.telegram_chat_id)
                .where(
                    Routine.is_active.is_(True),
                    Routine.next_run_at <= now,
                    ChatAccess.status == AccessStatus.ALLOWED,
                )
                .options(
                    joinedload(Routine.user),
                    selectinload(Routine.habits),
                    with_loader_criteria(Habit, Habit.archived_at.is_(None)),
                )
                .order_by(Routine.next_run_at)
            )
        )
        for routine in routines:
            await self._run_routine(routine, now, report)
        await self._close_expired(now, report)
        return report

    async def _run_routine(self, routine: Routine, now: datetime, report: TickReport) -> None:
        tz = get_zone(routine.user.timezone)
        schedule = routine_schedule(routine, routine.user.timezone)
        habit_ids = [habit.id for habit in routine.habits]
        to_send: list[Occurrence] = []

        for _ in range(MAX_CATCH_UP_RUNS):
            slot = routine.next_run_at
            if slot is None or slot > now:
                break
            routine.next_run_at = schedule.next_after(slot)
            if not habit_ids:
                continue
            already = await self.session.scalar(
                select(Occurrence.id).where(
                    Occurrence.routine_id == routine.id, Occurrence.scheduled_for == slot
                )
            )
            if already is not None:
                continue
            day = local_date(slot, tz)
            closes_at = day_end_utc(day, tz)
            late = now - slot > self.grace or closes_at <= now
            occurrence = Occurrence(
                routine_id=routine.id,
                scheduled_for=slot,
                local_date=day,
                closes_at=closes_at,
                status=OccurrenceStatus.MISSED if late else OccurrenceStatus.SENT,
                checks=[HabitCheck(habit_id=habit_id) for habit_id in habit_ids],
            )
            self.session.add(occurrence)
            if late:
                report.missed += 1
                logger.info("Routine %s run at %s missed", routine.id, slot.isoformat())
            else:
                to_send.append(occurrence)
        else:
            # Downtime longer than the catch-up window: jump straight to the future.
            routine.next_run_at = schedule.next_after(now)
        # Commit before sending: the unique (routine_id, scheduled_for) row guards "sent once".
        await self.session.commit()

        for occurrence_id in [occurrence.id for occurrence in to_send]:
            try:
                checklist = await self.checklists.build(occurrence_id, now)
                message_id = await self.notifier.send_checklist(checklist)
            except Exception:
                report.failed += 1
                logger.exception("Failed to send checklist for occurrence %s", occurrence_id)
                continue
            occurrence = await self.session.get_one(Occurrence, occurrence_id)
            occurrence.telegram_message_id = message_id
            await self.session.commit()
            report.sent += 1

    async def _close_expired(self, now: datetime, report: TickReport) -> None:
        expired = list(
            await self.session.scalars(
                select(Occurrence).where(
                    Occurrence.status == OccurrenceStatus.SENT, Occurrence.closes_at <= now
                )
            )
        )
        if not expired:
            return
        for occurrence in expired:
            occurrence.status = OccurrenceStatus.CLOSED
        await self.session.commit()
        report.closed += len(expired)

        for occurrence in expired:
            if occurrence.telegram_message_id is None:
                continue
            try:
                await self.notifier.close_checklist(await self.checklists.build(occurrence.id, now))
            except Exception:
                logger.warning("Failed to close checklist message %s", occurrence.id, exc_info=True)
