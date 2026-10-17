from datetime import date

from src.domain import milestone
from src.domain.enums import CheckStatus, DayOutcome, OccurrenceStatus
from src.domain.streak import (
    DayRecord,
    best_streak,
    completion_rate,
    compute_stats,
    current_streak,
    day_outcome,
)

D, N, S, P, M = (
    DayOutcome.DONE,
    DayOutcome.NOT_DONE,
    DayOutcome.SKIPPED,
    DayOutcome.PENDING,
    DayOutcome.MISSED,
)


def test_current_streak_counts_trailing_done() -> None:
    assert current_streak([D, N, D, D, D]) == 3


def test_open_day_does_not_break_streak() -> None:
    assert current_streak([D, D, P]) == 2


def test_skipped_breaks_streak() -> None:
    assert current_streak([D, D, S, D]) == 1


def test_system_missed_is_ignored() -> None:
    assert current_streak([D, M, D]) == 2
    assert best_streak([D, M, D, N, D]) == 2


def test_best_streak() -> None:
    assert best_streak([D, D, D, N, D, D]) == 3
    assert best_streak([]) == 0


def test_completion_rate_ignores_pending_and_missed() -> None:
    assert completion_rate([D, N, P, M]) == 0.5
    assert completion_rate([P]) is None


def test_day_outcome() -> None:
    sent, missed, closed = OccurrenceStatus.SENT, OccurrenceStatus.MISSED, OccurrenceStatus.CLOSED
    assert day_outcome(sent, CheckStatus.DONE, is_open=True) is D
    assert day_outcome(sent, CheckStatus.PENDING, is_open=True) is P
    assert day_outcome(sent, CheckStatus.PENDING, is_open=False) is N
    assert day_outcome(closed, CheckStatus.SKIPPED, is_open=False) is S
    assert day_outcome(missed, CheckStatus.PENDING, is_open=True) is M


def test_compute_stats_rate_window() -> None:
    records = [
        DayRecord(date(2026, 10, 1), N),
        DayRecord(date(2026, 10, 2), D),
        DayRecord(date(2026, 10, 3), D),
    ]
    stats = compute_stats(records, rate_since=date(2026, 10, 2))
    assert stats.current_streak == 2
    assert stats.completion_rate == 1.0


def test_milestones() -> None:
    assert milestone.reached(22) == [7, 14, 21]
    assert milestone.next_milestone(22) == milestone.NextMilestone(threshold=30, remaining=8)
    assert milestone.next_milestone(400) is None
    assert milestone.just_reached(21) == 21
    assert milestone.just_reached(22) is None
