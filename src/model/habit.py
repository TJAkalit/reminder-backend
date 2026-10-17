from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UTCDateTime
from src.domain.clock import now_utc

if TYPE_CHECKING:
    from src.model.routine import Routine


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(primary_key=True)
    routine_id: Mapped[int] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(1024))
    emoji: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    # Archived habits keep their history but are no longer included in new checklists.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    routine: Mapped[Routine] = relationship(back_populates="habits", lazy="raise")
    milestones: Mapped[list[HabitMilestone]] = relationship(
        back_populates="habit", lazy="raise", order_by="HabitMilestone.threshold"
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class HabitMilestone(Base):
    """A streak badge that, once achieved, is kept forever."""

    __tablename__ = "habit_milestones"
    __table_args__ = (UniqueConstraint("habit_id", "threshold"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    habit_id: Mapped[int] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), index=True)
    threshold: Mapped[int]
    achieved_on: Mapped[date] = mapped_column(Date)

    habit: Mapped[Habit] = relationship(back_populates="milestones", lazy="raise")
