from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from src.bot.keyboards import checklist_keyboard
from src.bot.texts import checklist_text
from src.dto.checklist import Checklist


def _is_not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in exc.message


class TelegramNotifier:
    """Telegram implementation of ``src.service.notifier.ChecklistNotifier``."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send_checklist(self, checklist: Checklist) -> int:
        message = await self.bot.send_message(
            chat_id=checklist.chat_id,
            text=checklist_text(checklist),
            reply_markup=checklist_keyboard(checklist),
        )
        return message.message_id

    async def update_checklist(self, checklist: Checklist) -> None:
        if checklist.message_id is None:
            return
        try:
            await self.bot.edit_message_text(
                text=checklist_text(checklist),
                chat_id=checklist.chat_id,
                message_id=checklist.message_id,
                reply_markup=checklist_keyboard(checklist),
            )
        except TelegramBadRequest as exc:
            if not _is_not_modified(exc):
                raise

    async def close_checklist(self, checklist: Checklist) -> None:
        await self.update_checklist(checklist.model_copy(update={"is_open": False}))

    async def remove_buttons(self, chat_id: int, message_id: int) -> None:
        try:
            await self.bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except TelegramBadRequest as exc:
            if not _is_not_modified(exc):
                raise
