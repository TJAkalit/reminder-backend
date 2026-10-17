"""Admin commands and access requests in Telegram (D-020)."""

import logging
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards import AccessCb, access_request_keyboard
from src.bot.texts import ADMIN_COMMANDS, access_line
from src.domain.enums import AccessStatus
from src.model import ChatAccess
from src.service.access import AccessService
from src.service.errors import ForbiddenError, NotFoundError

logger = logging.getLogger(__name__)


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, access: ChatAccess | None = None) -> bool:
        return access is not None and access.is_allowed and access.is_admin


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

GRANTED_TEXT = "✅ Доступ открыт! Нажмите /start, чтобы начать."


def request_text(entry: ChatAccess) -> str:
    return (
        f"🙋 Заявка на доступ: <b>{escape(entry.label)}</b>\n"
        f"chat_id: <code>{entry.telegram_chat_id}</code>"
    )


async def notify_new_request(bot: Bot, admin_chat_ids: list[int], entry: ChatAccess) -> None:
    for admin_chat_id in admin_chat_ids:
        try:
            await bot.send_message(
                admin_chat_id,
                request_text(entry),
                reply_markup=access_request_keyboard(entry.telegram_chat_id),
            )
        except TelegramAPIError:
            logger.warning("Could not notify admin %s", admin_chat_id, exc_info=True)


async def _tell(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except TelegramAPIError:
        logger.warning("Could not message chat %s", chat_id, exc_info=True)


def _parse_chat_id(command: CommandObject) -> int | None:
    args = (command.args or "").strip()
    return int(args) if args.lstrip("-").isdigit() else None


@router.message(Command("admin"))
async def admin_help(message: Message, session: AsyncSession) -> None:
    pending = await AccessService(session).entries(AccessStatus.PENDING)
    commands = "\n".join(f"/{name} — {text}" for name, text in ADMIN_COMMANDS.items())
    await message.answer(
        f"👑 <b>Администрирование</b>\nЗаявок на рассмотрении: {len(pending)}\n\n{commands}"
    )


@router.message(Command("users"))
async def users(message: Message, session: AsyncSession) -> None:
    entries = await AccessService(session).entries()
    sections = (
        ("Доступ есть", [e for e in entries if e.is_allowed]),
        ("Заявки", [e for e in entries if e.status is AccessStatus.PENDING]),
        ("Отклонены", [e for e in entries if e.status is AccessStatus.DENIED]),
    )
    blocks = [
        f"<b>{title}</b>\n" + "\n".join(access_line(e) for e in items)
        for title, items in sections
        if items
    ]
    await message.answer("\n\n".join(blocks) or "Пусто.")


@router.message(Command("requests"))
async def requests(message: Message, session: AsyncSession) -> None:
    pending = await AccessService(session).entries(AccessStatus.PENDING)
    if not pending:
        await message.answer("Заявок нет.")
        return
    for entry in pending:
        await message.answer(
            request_text(entry), reply_markup=access_request_keyboard(entry.telegram_chat_id)
        )


@router.message(Command("allow"))
async def allow(message: Message, command: CommandObject, session: AsyncSession) -> None:
    chat_id = _parse_chat_id(command)
    if chat_id is None:
        await message.answer("Формат: <code>/allow 123456789</code>")
        return
    entry = await AccessService(session).allow(chat_id, by_chat_id=message.chat.id)
    await message.answer(f"✅ Доступ открыт: {access_line(entry)}")
    if message.bot is not None:
        await _tell(message.bot, chat_id, GRANTED_TEXT)


@router.message(Command("revoke"))
async def revoke(message: Message, command: CommandObject, session: AsyncSession) -> None:
    chat_id = _parse_chat_id(command)
    if chat_id is None:
        await message.answer("Формат: <code>/revoke 123456789</code>")
        return
    try:
        entry = await AccessService(session).deny(chat_id, by_chat_id=message.chat.id)
    except NotFoundError:
        await message.answer("Такого chat_id нет в списке.")
        return
    except ForbiddenError as exc:
        reason = (
            "Нельзя закрыть доступ самому себе."
            if chat_id == message.chat.id
            else "Это администратор — сначала снимите права: "
            f"<code>uv run reminder admin demote {chat_id}</code>"
        )
        logger.info("Revoke refused: %s", exc)
        await message.answer(reason)
        return
    await message.answer(f"⛔ Доступ закрыт: {access_line(entry)}\nДанные пользователя сохранены.")


@router.callback_query(AccessCb.filter())
async def on_request_decision(
    callback: CallbackQuery, callback_data: AccessCb, session: AsyncSession
) -> None:
    message = callback.message
    service = AccessService(session)
    entry = await service.get(callback_data.chat_id)
    if entry is None or not isinstance(message, Message):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if entry.status is not AccessStatus.PENDING:
        verdict = "разрешена" if entry.is_allowed else "отклонена"
        await callback.answer(f"Заявка уже {verdict}")
        await message.edit_text(f"{request_text(entry)}\n\nУже {verdict}.")
        return

    admin_chat_id = message.chat.id
    if callback_data.action == "allow":
        entry = await service.allow(entry.telegram_chat_id, by_chat_id=admin_chat_id)
        await message.edit_text(f"{request_text(entry)}\n\n✅ Разрешено.")
        if callback.bot is not None:
            await _tell(callback.bot, entry.telegram_chat_id, GRANTED_TEXT)
    else:
        entry = await service.deny(entry.telegram_chat_id, by_chat_id=admin_chat_id)
        await message.edit_text(f"{request_text(entry)}\n\n⛔ Отклонено.")
    await callback.answer()
