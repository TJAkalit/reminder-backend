"""Bot access: requests, decisions and admins (D-020)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.clock import now_utc
from src.domain.enums import AccessStatus
from src.model import ChatAccess
from src.service.errors import ForbiddenError, NotFoundError, ValidationError


@dataclass(frozen=True, slots=True)
class RequestResult:
    entry: ChatAccess
    # True when a new request was created and admins should be notified.
    created: bool


class AccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, chat_id: int) -> ChatAccess | None:
        return await self.session.scalar(
            select(ChatAccess).where(ChatAccess.telegram_chat_id == chat_id)
        )

    async def is_allowed(self, chat_id: int) -> bool:
        entry = await self.get(chat_id)
        return entry is not None and entry.is_allowed

    async def entries(self, status: AccessStatus | None = None) -> list[ChatAccess]:
        query = select(ChatAccess).order_by(
            ChatAccess.is_admin.desc(), ChatAccess.status, ChatAccess.requested_at
        )
        if status is not None:
            query = query.where(ChatAccess.status == status)
        return list(await self.session.scalars(query))

    async def admin_chat_ids(self) -> list[int]:
        return list(
            await self.session.scalars(
                select(ChatAccess.telegram_chat_id).where(
                    ChatAccess.is_admin.is_(True), ChatAccess.status == AccessStatus.ALLOWED
                )
            )
        )

    async def request(
        self, chat_id: int, display_name: str | None, username: str | None
    ) -> RequestResult:
        """Register a request from an unknown chat. Repeated messages do not re-notify admins."""
        entry = await self.get(chat_id)
        if entry is not None:
            if entry.display_name is None and display_name:
                entry.display_name, entry.username = display_name, username
                await self.session.commit()
            return RequestResult(entry, created=False)
        entry = ChatAccess(
            telegram_chat_id=chat_id,
            status=AccessStatus.PENDING,
            display_name=display_name,
            username=username,
        )
        self.session.add(entry)
        await self.session.commit()
        return RequestResult(entry, created=True)

    async def allow(
        self,
        chat_id: int,
        *,
        by_chat_id: int | None,
        display_name: str | None = None,
        now: datetime | None = None,
    ) -> ChatAccess:
        """Grant access; works for pending requests and for chats that never wrote yet."""
        entry = await self.get(chat_id)
        if entry is None:
            entry = ChatAccess(telegram_chat_id=chat_id, display_name=display_name)
            self.session.add(entry)
        entry.status = AccessStatus.ALLOWED
        entry.decided_at = now or now_utc()
        entry.decided_by_chat_id = by_chat_id
        await self.session.commit()
        return entry

    async def deny(
        self, chat_id: int, *, by_chat_id: int | None, now: datetime | None = None
    ) -> ChatAccess:
        """Reject a request or revoke access. Admins must be demoted first."""
        entry = await self.get(chat_id)
        if entry is None:
            raise NotFoundError(f"Chat {chat_id} is unknown")
        if chat_id == by_chat_id:
            raise ForbiddenError("You cannot revoke your own access")
        if entry.is_admin:
            raise ForbiddenError("Demote the admin first")
        entry.status = AccessStatus.DENIED
        entry.decided_at = now or now_utc()
        entry.decided_by_chat_id = by_chat_id
        await self.session.commit()
        return entry

    async def set_admin(self, chat_id: int, is_admin: bool) -> ChatAccess:
        """Promote (also grants access) or demote. The last admin cannot be demoted."""
        if is_admin:
            entry = await self.allow(chat_id, by_chat_id=None)
            entry.is_admin = True
            await self.session.commit()
            return entry
        existing = await self.get(chat_id)
        if existing is None:
            raise NotFoundError(f"Chat {chat_id} is unknown")
        if existing.is_admin:
            admins = await self.session.scalar(
                select(func.count()).select_from(ChatAccess).where(ChatAccess.is_admin.is_(True))
            )
            if admins == 1:
                raise ValidationError("This is the last admin")
            existing.is_admin = False
            await self.session.commit()
        return existing
