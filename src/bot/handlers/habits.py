from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.common import NOT_REGISTERED
from src.bot.keyboards import ArchiveCb, archive_confirm_keyboard, archive_pick_keyboard
from src.bot.texts import habits_text, with_emoji
from src.model import User
from src.service.errors import NotFoundError
from src.service.habit import HabitService
from src.service.routine import RoutineService

router = Router(name="habits")


@router.message(Command("habits"))
async def habits(message: Message, session: AsyncSession, user: User | None) -> None:
    if user is None:
        await message.answer(NOT_REGISTERED)
        return
    routines = await RoutineService(session).list_out(user)
    habit_list = await HabitService(session).list_out(user)
    await message.answer(habits_text(routines, habit_list))


@router.message(Command("archive"))
async def archive(message: Message, session: AsyncSession, user: User | None) -> None:
    if user is None:
        await message.answer(NOT_REGISTERED)
        return
    active = await HabitService(session).list_active(user)
    if not active:
        await message.answer("Активных привычек нет.")
        return
    await message.answer(
        "Какую привычку убрать в архив?", reply_markup=archive_pick_keyboard(active)
    )


@router.callback_query(ArchiveCb.filter())
async def on_archive(
    callback: CallbackQuery, callback_data: ArchiveCb, session: AsyncSession, user: User | None
) -> None:
    message = callback.message
    if user is None or message is None or not isinstance(message, Message):
        await callback.answer()
        return
    service = HabitService(session)
    try:
        match callback_data.action:
            case "pick":
                habit = await service.get_owned(user, callback_data.habit_id)
                await message.edit_text(
                    f"Убрать «{escape(with_emoji(habit.title, habit.emoji))}» в архив?\n"
                    "История и серии сохранятся, в чек-листах привычки больше не будет.",
                    reply_markup=archive_confirm_keyboard(habit.id),
                )
            case "yes":
                habit = await service.archive(user, callback_data.habit_id)
                await message.edit_text(
                    f"🗄 «{escape(with_emoji(habit.title, habit.emoji))}» в архиве."
                )
            case _:
                await message.edit_text("Отменено.")
    except NotFoundError:
        await message.edit_text("Привычка не найдена.")
    await callback.answer()
