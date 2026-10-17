from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.common import NOT_REGISTERED
from src.bot.keyboards import CheckCb
from src.bot.notifier import TelegramNotifier
from src.bot.texts import STATUS_MARK, milestone_text
from src.domain.clock import get_zone
from src.dto.today import TodayState
from src.model import User
from src.service.checklist import ChecklistService
from src.service.errors import ChecklistClosedError, ForbiddenError, NotFoundError
from src.service.today import TodayService

router = Router(name="checklist")


@router.callback_query(CheckCb.filter())
async def on_check(
    callback: CallbackQuery,
    callback_data: CheckCb,
    session: AsyncSession,
    notifier: TelegramNotifier,
) -> None:
    if callback.message is None:
        await callback.answer("Сообщение устарело")
        return
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    try:
        result = await ChecklistService(session).toggle(
            chat_id, callback_data.occurrence_id, callback_data.habit_id
        )
    except ChecklistClosedError:
        await callback.answer("День закрыт — отметки больше не принимаются", show_alert=True)
        await notifier.remove_buttons(chat_id, message_id)
        return
    except NotFoundError, ForbiddenError:
        await callback.answer("Чек-лист не найден", show_alert=True)
        return

    await notifier.update_checklist(result.checklist.model_copy(update={"message_id": message_id}))
    checklist = result.checklist
    if checklist.items and checklist.done_count == len(checklist.items):
        await callback.answer("Всё выполнено! 🎉")
    else:
        await callback.answer(f"{STATUS_MARK[result.new_status]} {result.habit_title}")
    if result.milestone is not None:
        await callback.message.answer(milestone_text(result.habit_title, result.milestone))


@router.message(Command("today"))
async def today(
    message: Message, session: AsyncSession, user: User | None, notifier: TelegramNotifier
) -> None:
    if user is None:
        await message.answer(NOT_REGISTERED)
        return
    sent = await ChecklistService(session).resend_today(user, notifier)
    if sent:
        return
    overview = await TodayService(session).get(user)
    if not overview.routines:
        await message.answer("Сегодня по расписанию ничего нет. Добавить привычку: /add")
        return
    lines = []
    for routine in overview.routines:
        title = escape(routine.title)
        if routine.state is TodayState.UPCOMING and routine.scheduled_at:
            at = routine.scheduled_at.astimezone(get_zone(user.timezone)).strftime("%H:%M")
            lines.append(f"• {title} — пришлю в {at}")
        else:
            lines.append(f"• {title} — {escape(routine.schedule_description)}")
    await message.answer("Сегодня:\n" + "\n".join(lines))
