"""Milestone badges for streak lengths (D-017)."""

from dataclasses import dataclass

THRESHOLDS: tuple[int, ...] = (7, 14, 21, 30, 66, 100, 180, 365)


@dataclass(frozen=True, slots=True)
class NextMilestone:
    threshold: int
    remaining: int


def reached(streak: int) -> list[int]:
    return [t for t in THRESHOLDS if t <= streak]


def next_milestone(streak: int) -> NextMilestone | None:
    for threshold in THRESHOLDS:
        if threshold > streak:
            return NextMilestone(threshold=threshold, remaining=threshold - streak)
    return None


def just_reached(streak: int) -> int | None:
    """The threshold hit exactly by this streak value, if any."""
    return streak if streak in THRESHOLDS else None
