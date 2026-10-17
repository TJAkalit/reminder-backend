from datetime import datetime

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, UTCDateTime, str_enum
from src.domain.clock import now_utc
from src.domain.enums import AccessStatus


class ChatAccess(Base):
    """Who may use the bot (D-020).

    Keyed by Telegram chat id rather than a user row: access can be granted before the person
    ever writes to the bot, and a pending request exists before any user is registered.
    """

    __tablename__ = "chat_access"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    status: Mapped[AccessStatus] = mapped_column(str_enum(AccessStatus))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Known from the request message; empty for entries added by chat id.
    display_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decided_by_chat_id: Mapped[int | None] = mapped_column(BigInteger)

    @property
    def is_allowed(self) -> bool:
        return self.status is AccessStatus.ALLOWED

    @property
    def label(self) -> str:
        name = self.display_name or "без имени"
        return f"{name} (@{self.username})" if self.username else name
