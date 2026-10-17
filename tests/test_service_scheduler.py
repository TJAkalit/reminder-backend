from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.enums import CheckStatus, DayOutcome, OccurrenceStatus
from src.dto.today import TodayState
from src.model import HabitMilestone, Occurrence
from src.service.checklist import ChecklistService
from src.service.errors import ChecklistClosedError, ForbiddenError
from src.service.habit import HabitService
from src.service.scheduler import SchedulerService
from src.service.today import TodayService
from tests.conftest import T0, FakeNotifier, World

GRACE = timedelta(hours=2)
# 07:00 MSK on 2026-10-18
RUN = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def scheduler(session: AsyncSession, notifier: FakeNotifier) -> SchedulerService:
    return SchedulerService(session, notifier, GRACE)


async def occurrences(session: AsyncSession) -> list[Occurrence]:
    return list(await session.scalars(select(Occurrence).order_by(Occurrence.scheduled_for)))


async def test_next_run_is_computed_on_create(world: World) -> None:
    assert world.routine.next_run_at == RUN


async def test_tick_before_run_does_nothing(session, world, notifier) -> None:
    report = await scheduler(session, notifier).tick(RUN - timedelta(minutes=1))
    assert report.sent == 0
    assert await occurrences(session) == []


async def test_tick_sends_checklist_once(session, world, notifier) -> None:
    report = await scheduler(session, notifier).tick(RUN + timedelta(seconds=10))
    assert report.sent == 1
    (checklist,) = notifier.sent
    assert checklist.chat_id == 111
    assert [i.title for i in checklist.items] == ["Стакан воды", "Зарядка"]
    assert checklist.is_open

    (occ,) = await occurrences(session)
    assert occ.status is OccurrenceStatus.SENT
    assert occ.telegram_message_id == 101
    assert occ.local_date.isoformat() == "2026-10-18"
    assert occ.closes_at == datetime(2026, 10, 18, 21, 0, tzinfo=UTC)  # midnight MSK

    again = await scheduler(session, notifier).tick(RUN + timedelta(seconds=40))
    assert again.sent == 0
    assert len(notifier.sent) == 1
    await session.refresh(world.routine)
    assert world.routine.next_run_at == RUN + DAY


async def test_late_run_is_missed(session, world, notifier) -> None:
    report = await scheduler(session, notifier).tick(RUN + GRACE + timedelta(minutes=1))
    assert report.missed == 1
    assert notifier.sent == []
    (occ,) = await occurrences(session)
    assert occ.status is OccurrenceStatus.MISSED


async def test_catch_up_after_downtime(session, world, notifier) -> None:
    # Worker comes back on day 3 at 07:30: two missed days and today's run is sent.
    report = await scheduler(session, notifier).tick(RUN + 2 * DAY + timedelta(minutes=30))
    assert (report.missed, report.sent) == (2, 1)
    statuses = [o.status for o in await occurrences(session)]
    assert statuses == [OccurrenceStatus.MISSED, OccurrenceStatus.MISSED, OccurrenceStatus.SENT]


async def test_send_failure_keeps_occurrence(session, world, notifier) -> None:
    notifier.fail = True
    report = await scheduler(session, notifier).tick(RUN)
    assert report.failed == 1
    (occ,) = await occurrences(session)
    assert occ.status is OccurrenceStatus.SENT and occ.telegram_message_id is None


async def test_day_closes_at_local_midnight(session, world, notifier) -> None:
    await scheduler(session, notifier).tick(RUN)
    report = await scheduler(session, notifier).tick(datetime(2026, 10, 18, 21, 0, tzinfo=UTC))
    assert report.closed == 1
    assert len(notifier.closed) == 1 and not notifier.closed[0].is_open
    (occ,) = await occurrences(session)
    assert occ.status is OccurrenceStatus.CLOSED


async def test_toggle_cycles_status(session, world, notifier) -> None:
    await scheduler(session, notifier).tick(RUN)
    (occ,) = await occurrences(session)
    service = ChecklistService(session)
    water = world.habits[0].id

    result = await service.toggle(111, occ.id, water, RUN + timedelta(minutes=5))
    assert result.new_status is CheckStatus.DONE
    assert result.checklist.items[0].current_streak == 1
    assert result.checklist.done_count == 1

    result = await service.toggle(111, occ.id, water, RUN + timedelta(minutes=6))
    assert result.new_status is CheckStatus.SKIPPED
    result = await service.toggle(111, occ.id, water, RUN + timedelta(minutes=7))
    assert result.new_status is CheckStatus.PENDING


async def test_toggle_rejects_closed_day_and_strangers(session, world, notifier) -> None:
    await scheduler(session, notifier).tick(RUN)
    (occ,) = await occurrences(session)
    service = ChecklistService(session)
    with pytest.raises(ForbiddenError):
        await service.toggle(999, occ.id, world.habits[0].id, RUN)
    with pytest.raises(ChecklistClosedError):
        await service.toggle(111, occ.id, world.habits[0].id, RUN + DAY)


async def test_streak_and_milestone_over_a_week(session, world, notifier) -> None:
    water, workout = (h.id for h in world.habits)
    service = ChecklistService(session)
    result = None
    for day in range(7):
        now = RUN + day * DAY
        await scheduler(session, notifier).tick(now)
        occ = (await occurrences(session))[-1]
        result = await service.toggle(111, occ.id, water, now + timedelta(minutes=1))
        if day == 3:
            await service.toggle(111, occ.id, workout, now + timedelta(minutes=1))
    assert result is not None
    assert result.milestone == 7
    assert result.checklist.items[0].current_streak == 7

    stored = list(await session.scalars(select(HabitMilestone.threshold)))
    assert stored == [7]

    now = RUN + 6 * DAY + timedelta(hours=1)
    habits = {h.id: h for h in await HabitService(session).list_out(world.user, now=now)}
    assert habits[water].stats.current_streak == 7
    assert habits[water].stats.best_streak == 7
    upcoming = habits[water].stats.next_milestone
    assert upcoming is not None and upcoming.threshold == 14
    # Workout was done only on day 3; today (day 6) is still open, so it is 1/6 closed days.
    assert habits[workout].stats.current_streak == 0
    assert habits[workout].stats.best_streak == 1
    assert habits[workout].stats.completion_rate_30d == pytest.approx(1 / 6)

    history = await HabitService(session).history(world.user, workout, now=now)
    outcomes = [d.outcome for d in history.days]
    assert outcomes[3] is DayOutcome.DONE
    assert outcomes[-1] is DayOutcome.PENDING
    assert outcomes.count(DayOutcome.NOT_DONE) == 5


async def test_archived_habit_is_not_in_new_checklists(session, world, notifier) -> None:
    await HabitService(session).archive(world.user, world.habits[1].id, T0)
    await scheduler(session, notifier).tick(RUN)
    assert [i.title for i in notifier.sent[0].items] == ["Стакан воды"]


async def test_resend_today_revives_missed(session, world, notifier) -> None:
    await scheduler(session, notifier).tick(RUN + GRACE + timedelta(minutes=1))
    sent = await ChecklistService(session).resend_today(
        world.user, notifier, RUN + timedelta(hours=3)
    )
    assert len(sent) == 1 and sent[0].message_id == 101
    (occ,) = await occurrences(session)
    assert occ.status is OccurrenceStatus.SENT


async def test_today_states(session, world, notifier) -> None:
    today = await TodayService(session).get(world.user, T0)
    (routine,) = today.routines
    assert routine.state is TodayState.UPCOMING
    assert routine.scheduled_at == RUN

    today = await TodayService(session).get(world.user, RUN + timedelta(minutes=1))
    assert today.routines[0].state is TodayState.NOT_SENT

    await scheduler(session, notifier).tick(RUN)
    today = await TodayService(session).get(world.user, RUN + timedelta(minutes=1))
    assert today.routines[0].state is TodayState.OPEN
    assert today.routines[0].occurrence_id is not None
    assert [i.status for i in today.routines[0].items] == [CheckStatus.PENDING] * 2
