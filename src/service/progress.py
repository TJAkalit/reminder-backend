"""Loads habit history from the database and turns it into domain streak records."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain import milestone
from src.domain.enums import OccurrenceStatus
from src.domain.streak import DayRecord, HabitStats, compute_stats, day_outcome
from src.dto.habit import HabitStatsOut, MilestoneOut, NextMilestoneOut
from src.model import HabitCheck, HabitMilestone, Occurrence

RATE_WINDOW_DAYS = 30


async def load_records(
    session: AsyncSession, habit_ids: Iterable[int], now: datetime
) -> dict[int, list[DayRecord]]:
    """Per-habit day records ordered from oldest to newest."""
    ids = list(habit_ids)
    records: dict[int, list[DayRecord]] = defaultdict(list)
    if not ids:
        return records
    rows = await session.execute(
        select(
            HabitCheck.habit_id,
            HabitCheck.status,
            Occurrence.status,
            Occurrence.closes_at,
            Occurrence.local_date,
        )
        .join(Occurrence, HabitCheck.occurrence_id == Occurrence.id)
        .where(HabitCheck.habit_id.in_(ids))
        .order_by(Occurrence.scheduled_for)
    )
    for habit_id, check_status, occ_status, closes_at, day in rows:
        is_open = occ_status is OccurrenceStatus.SENT and now < closes_at
        records[habit_id].append(
            DayRecord(day, day_outcome(occ_status, check_status, is_open=is_open))
        )
    return records


async def load_milestones(
    session: AsyncSession, habit_ids: Iterable[int]
) -> dict[int, list[HabitMilestone]]:
    ids = list(habit_ids)
    result: dict[int, list[HabitMilestone]] = defaultdict(list)
    if not ids:
        return result
    rows = await session.scalars(
        select(HabitMilestone)
        .where(HabitMilestone.habit_id.in_(ids))
        .order_by(HabitMilestone.threshold)
    )
    for row in rows:
        result[row.habit_id].append(row)
    return result


def stats(records: list[DayRecord], today: date) -> HabitStats:
    return compute_stats(records, rate_since=today - timedelta(days=RATE_WINDOW_DAYS - 1))


def stats_out(habit_stats: HabitStats, achieved: list[HabitMilestone]) -> HabitStatsOut:
    upcoming = milestone.next_milestone(habit_stats.current_streak)
    return HabitStatsOut(
        current_streak=habit_stats.current_streak,
        best_streak=habit_stats.best_streak,
        completion_rate_30d=habit_stats.completion_rate,
        milestones=[
            MilestoneOut(threshold=m.threshold, achieved_on=m.achieved_on) for m in achieved
        ],
        next_milestone=(
            NextMilestoneOut(threshold=upcoming.threshold, remaining=upcoming.remaining)
            if upcoming
            else None
        ),
    )
