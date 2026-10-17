import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.handlers.admin import notify_new_request
from src.domain.enums import AccessStatus
from src.model import ChatAccess
from src.service.access import AccessService
from src.service.user import UserService

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class AccessMiddleware(BaseMiddleware):
    """Opens a DB session per update and lets only allowed chats through (D-020).

    Handlers receive ``session``, ``access`` (ChatAccess of the chat) and ``user`` (or None).
    A message from an unknown chat becomes an access request that admins see in Telegram.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        chat: Chat | None = data.get("event_chat")
        async with self.session_factory() as session:
            data["session"] = session
            data["access"] = data["user"] = None
            if chat is None:
                return await handler(event, data)
            entry = await AccessService(session).get(chat.id)
            if entry is not None and entry.is_allowed:
                data["access"] = entry
                data["user"] = await UserService(session).get_by_chat_id(chat.id)
                return await handler(event, data)
            await self._reject(event, data["bot"], session, entry, chat)
            return None

    async def _reject(
        self,
        event: TelegramObject,
        bot: Bot,
        session: AsyncSession,
        entry: ChatAccess | None,
        chat: Chat,
    ) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer("Доступ закрыт", show_alert=True)
            return
        if not isinstance(event, Message):
            return
        if entry is not None and entry.status is AccessStatus.DENIED:
            await event.answer("Доступ закрыт.")
            return

        service = AccessService(session)
        sender = event.from_user
        result = await service.request(
            chat.id, sender.full_name if sender else None, sender.username if sender else None
        )
        admins = await service.admin_chat_ids()
        if not admins:
            logger.warning("Access request from chat %s, but there are no admins", chat.id)
            await event.answer(
                "Администратор ещё не назначен.\n"
                f"Ваш chat_id: <code>{chat.id}</code>\n"
                f"Назначить себя: <code>uv run reminder admin grant {chat.id}</code>"
            )
            return
        if result.created:
            logger.info("New access request from chat %s", chat.id)
            await notify_new_request(bot, admins, result.entry)
            await event.answer(
                "Привет! Это приватный бот — я отправил заявку администратору.\n"
                "Напишу, как только доступ откроют."
            )
        else:
            await event.answer("Заявка уже у администратора, ждём решения.")
