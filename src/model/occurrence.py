from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UTCDateTime, str_enum
from src.domain.clock import now_utc
from src.domain.enums import CheckStatus, OccurrenceStatus

if TYPE_CHECKING:
    from src.model.habit import Habit
    from src.model.routine import Routine


class Occurrence(Base):
    """One run of a routine («Утро, 18 окт»): a checklist open until the end of the local day."""

    __tablename__ = "occurrences"
    # Guarantees a routine run is created (and sent) only once, even after restarts.
    __table_args__ = (UniqueConstraint("routine_id", "scheduled_for"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"), index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    # Start of the next local day; checks are accepted until then (D-018).
    closes_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[OccurrenceStatus] = mapped_column(str_enum(OccurrenceStatus))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    routine: Mapped[Routine] = relationship(lazy="raise")
    checks: Mapped[list[HabitCheck]] = relationship(back_populates="occurrence", lazy="raise")

    def is_open(self, now: datetime) -> bool:
        return self.status is OccurrenceStatus.SENT and now < self.closes_at


class HabitCheck(Base):
    """A habit's status within one occurrence.

    Rows are created for every active habit when the occurrence is created, so the set of
    rows is a snapshot of what was on that day's checklist.
    """

    __tablename__ = "habit_checks"
    __table_args__ = (UniqueConstraint("occurrence_id", "habit_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    occurrence_id: Mapped[int] = mapped_column(
        ForeignKey("occurrences.id", ondelete="CASCADE"), index=True
    )
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    status: Mapped[CheckStatus] = mapped_column(str_enum(CheckStatus), default=CheckStatus.PENDING)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    occurrence: Mapped[Occurrence] = relationship(back_populates="checks", lazy="raise")
    habit: Mapped[Habit] = relationship(lazy="raise")
