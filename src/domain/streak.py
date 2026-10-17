"""Streak rules (see docs/domain.md, D-009, D-014, D-018).

A streak is counted over *scheduled occurrences* of the habit's routine, not calendar days:
- DONE extends the streak;
- NOT_DONE and SKIPPED (a closed day without "done") break it;
- PENDING (today, still open) neither extends nor breaks it;
- MISSED (the system failed to send the checklist) is ignored.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from src.domain.enums import CheckStatus, DayOutcome, OccurrenceStatus

_BREAKS = {DayOutcome.NOT_DONE, DayOutcome.SKIPPED}


def day_outcome(occurrence: OccurrenceStatus, check: CheckStatus, *, is_open: bool) -> DayOutcome:
    if check is CheckStatus.DONE:
        return DayOutcome.DONE
    if occurrence is OccurrenceStatus.MISSED:
        return DayOutcome.MISSED
    if is_open:
        return DayOutcome.PENDING
    if check is CheckStatus.SKIPPED:
        return DayOutcome.SKIPPED
    return DayOutcome.NOT_DONE


@dataclass(frozen=True, slots=True)
class DayRecord:
    day: date
    outcome: DayOutcome


@dataclass(frozen=True, slots=True)
class HabitStats:
    current_streak: int
    best_streak: int
    # Share of done days among days that count (closed or done), None if nothing counted yet.
    completion_rate: float | None


def current_streak(outcomes: Sequence[DayOutcome]) -> int:
    """``outcomes`` are ordered from oldest to newest."""
    streak = 0
    for outcome in reversed(outcomes):
        if outcome is DayOutcome.DONE:
            streak += 1
        elif outcome in _BREAKS:
            break
    return streak


def best_streak(outcomes: Sequence[DayOutcome]) -> int:
    best = run = 0
    for outcome in outcomes:
        if outcome is DayOutcome.DONE:
            run += 1
            best = max(best, run)
        elif outcome in _BREAKS:
            run = 0
    return best


def completion_rate(outcomes: Sequence[DayOutcome]) -> float | None:
    counted = [o for o in outcomes if o is DayOutcome.DONE or o in _BREAKS]
    if not counted:
        return None
    done = sum(1 for o in counted if o is DayOutcome.DONE)
    return done / len(counted)


def compute_stats(records: Sequence[DayRecord], *, rate_since: date | None = None) -> HabitStats:
    outcomes = [r.outcome for r in records]
    recent = outcomes if rate_since is None else [r.outcome for r in records if r.day >= rate_since]
    return HabitStats(
        current_streak=current_streak(outcomes),
        best_streak=best_streak(outcomes),
        completion_rate=completion_rate(recent),
    )
