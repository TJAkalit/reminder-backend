from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.clock import is_valid_timezone, now_utc
from src.domain.enums import AccessStatus
from src.dto.user import UserOut
from src.model import ChatAccess, Routine, User
from src.service.errors import ValidationError
from src.service.schedule import routine_schedule


def _with_access(query: Select[tuple[User]]) -> Select[tuple[User]]:
    """Only users whose chat currently has access (D-020)."""
    return query.join(ChatAccess, ChatAccess.telegram_chat_id == User.telegram_chat_id).where(
        ChatAccess.status == AccessStatus.ALLOWED
    )


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_users(self) -> list[UserOut]:
        users = await self.session.scalars(
            _with_access(select(User)).order_by(User.display_name, User.id)
        )
        return [UserOut.model_validate(user) for user in users]

    async def get(self, user_id: int) -> User | None:
        """A user with access; revoked users are invisible to the API."""
        user: User | None = await self.session.scalar(
            _with_access(select(User)).where(User.id == user_id)
        )
        return user

    async def get_by_chat_id(self, chat_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.telegram_chat_id == chat_id))

    async def register(self, chat_id: int, display_name: str, timezone: str) -> tuple[User, bool]:
        """Create the user for a Telegram chat; returns (user, created)."""
        user = await self.get_by_chat_id(chat_id)
        if user is not None:
            if user.display_name != display_name:
                user.display_name = display_name
                await self.session.commit()
            return user, False
        if not is_valid_timezone(timezone):
            raise ValidationError(f"Unknown timezone: {timezone}")
        user = User(telegram_chat_id=chat_id, display_name=display_name, timezone=timezone)
        self.session.add(user)
        await self.session.commit()
        return user, True

    async def set_timezone(self, user: User, timezone: str, now: datetime | None = None) -> None:
        if not is_valid_timezone(timezone):
            raise ValidationError(f"Unknown timezone: {timezone}")
        now = now or now_utc()
        user.timezone = timezone
        routines = await self.session.scalars(select(Routine).where(Routine.user_id == user.id))
        for routine in routines:
            routine.next_run_at = routine_schedule(routine, timezone).next_after(now)
        await self.session.commit()
