from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UTCDateTime, str_enum
from src.domain.clock import now_utc
from src.domain.enums import ScheduleKind

if TYPE_CHECKING:
    from src.model.habit import Habit
    from src.model.user import User


class Routine(Base):
    """A group of habits sharing one schedule; each run sends one checklist message."""

    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128))
    emoji: Mapped[str | None] = mapped_column(String(16))
    schedule_kind: Mapped[ScheduleKind] = mapped_column(
        str_enum(ScheduleKind), default=ScheduleKind.RRULE
    )
    # Local wall-clock rule without DTSTART, e.g. FREQ=DAILY;BYHOUR=7;BYMINUTE=0.
    schedule_rrule: Mapped[str] = mapped_column(String(255))
    # Local date the rule is anchored to (DTSTART at 00:00 local time).
    schedule_start: Mapped[date] = mapped_column(Date)
    # Next run in UTC; None when the rule is exhausted. Maintained by the scheduler.
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    user: Mapped[User] = relationship(back_populates="routines", lazy="raise")
    habits: Mapped[list[Habit]] = relationship(
        back_populates="routine", lazy="raise", order_by="Habit.sort_order, Habit.id"
    )
