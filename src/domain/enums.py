from enum import StrEnum


class OccurrenceStatus(StrEnum):
    # The checklist message was sent (or at least attempted) and the day is open.
    SENT = "sent"
    # The worker was down past the grace period; nothing was sent. Does not affect streaks.
    MISSED = "missed"
    # The local day of the occurrence is over; checks can no longer be changed.
    CLOSED = "closed"


class CheckStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"


class ScheduleKind(StrEnum):
    RRULE = "rrule"


class DayOutcome(StrEnum):
    """What a single scheduled occurrence means for one habit's history."""

    DONE = "done"
    SKIPPED = "skipped"
    NOT_DONE = "not_done"
    # The day is still open and the habit is not done yet.
    PENDING = "pending"
    # System failure: the checklist was never sent.
    MISSED = "missed"


class AccessStatus(StrEnum):
    # Somebody wrote to the bot and waits for an admin decision.
    PENDING = "pending"
    ALLOWED = "allowed"
    # Rejected request or revoked access.
    DENIED = "denied"
