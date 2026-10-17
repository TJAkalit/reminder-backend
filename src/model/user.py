from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, UTCDateTime
from src.domain.clock import now_utc

if TYPE_CHECKING:
    from src.model.routine import Routine


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)

    routines: Mapped[list[Routine]] = relationship(
        back_populates="user", lazy="raise", order_by="Routine.sort_order, Routine.id"
    )
