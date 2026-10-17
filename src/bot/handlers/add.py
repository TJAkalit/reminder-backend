"""Interactive /add dialog (D-016).

title → existing routine | new routine (title → preset → time) → confirm.
Button steps edit the same bot message; after a text answer the dialog continues in a new
message and the previous prompt loses its buttons.
"""

import contextlib
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.handlers.common import NOT_REGISTERED
from src.bot.keyboards import (
    AddCb,
    add_cancel_keyboard,
    add_confirm_keyboard,
    add_preset_keyboard,
    add_routine_keyboard,
    add_time_keyboard,
)
from src.bot.parsing import parse_time, split_emoji
from src.bot.texts import with_emoji
from src.domain.schedule import SchedulePreset, describe_rrule, preset_rrule
from src.model import User
from src.service.errors import NotFoundError
from src.service.habit import HabitService
from src.service.routine import RoutineService

router = Router(name="add")


class AddHabit(StatesGroup):
    title = State()
    routine = State()
    routine_title = State()
    preset = State()
    time = State()
    custom_time = State()
    confirm = State()


async def _prompt(
    message: Message, state: FSMContext, text: str, markup: InlineKeyboardMarkup
) -> None:
    """Continue the dialog in a new message, detaching the previous prompt."""
    data = await state.get_data()
    previous = data.get("prompt_id")
    if previous is not None and message.bot is not None:
        await _detach(message.bot, message.chat.id, previous)
    sent = await message.answer(text, reply_markup=markup)
    await state.update_data(prompt_id=sent.message_id)


async def _detach(bot: Bot, chat_id: int, message_id: int) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )


def _title(data: dict[str, Any]) -> str:
    return escape(with_emoji(data["title"], data.get("emoji")))


@router.message(Command("add"))
async def add(message: Message, state: FSMContext, user: User | None) -> None:
    if user is None:
        await message.answer(NOT_REGISTERED)
        return
    await state.clear()
    await state.set_state(AddHabit.title)
    await _prompt(
        message,
        state,
        "Как называется привычка?\n<i>Можно начать с эмодзи: «💧 Стакан воды»</i>",
        add_cancel_keyboard(),
    )


@router.message(AddHabit.title, F.text)
async def got_title(
    message: Message, state: FSMContext, session: AsyncSession, user: User | None
) -> None:
    assert message.text is not None and user is not None
    emoji, title = split_emoji(message.text)
    await state.update_data(title=title[:128], emoji=emoji)
    routines = await RoutineService(session).list_routines(user)
    if not routines:
        await state.set_state(AddHabit.routine_title)
        await _prompt(
            message,
            state,
            f"«{escape(title)}» — нужна рутина: группа привычек с общим расписанием.\n"
            "Как её назвать? <i>Например: «🌅 Утро»</i>",
            add_cancel_keyboard(),
        )
        return
    await state.set_state(AddHabit.routine)
    await _prompt(
        message,
        state,
        f"В какую рутину добавить «{escape(title)}»?",
        add_routine_keyboard(routines),
    )


@router.message(AddHabit.routine_title, F.text)
async def got_routine_title(message: Message, state: FSMContext) -> None:
    assert message.text is not None
    emoji, title = split_emoji(message.text)
    await state.update_data(routine_title=title[:128], routine_emoji=emoji)
    await state.set_state(AddHabit.preset)
    await _prompt(message, state, "Когда напоминать?", add_preset_keyboard())


@router.message(AddHabit.custom_time, F.text)
async def got_custom_time(message: Message, state: FSMContext) -> None:
    assert message.text is not None
    at = parse_time(message.text)
    if at is None:
        await message.answer("Не понял время. Формат: <code>07:45</code>")
        return
    await _ask_new_routine_confirm(message, state, at.hour, at.minute, new_message=True)


async def _ask_new_routine_confirm(
    message: Message, state: FSMContext, hour: int, minute: int, *, new_message: bool
) -> None:
    data = await state.get_data()
    rrule = preset_rrule(SchedulePreset(data["preset"]), hour, minute)
    await state.update_data(rrule=rrule, routine_id=None)
    await state.set_state(AddHabit.confirm)
    routine = escape(with_emoji(data["routine_title"], data.get("routine_emoji")))
    text = (
        f"Создать рутину «{routine}» ({describe_rrule(rrule)}) и добавить в неё «{_title(data)}»?"
    )
    markup = add_confirm_keyboard("✅ Создать")
    if new_message:
        await _prompt(message, state, text, markup)
    else:
        await message.edit_text(text, reply_markup=markup)


@router.callback_query(AddCb.filter())
async def on_add_button(
    callback: CallbackQuery,
    callback_data: AddCb,
    state: FSMContext,
    session: AsyncSession,
    user: User | None,
) -> None:
    message = callback.message
    await callback.answer()
    if user is None or message is None or not isinstance(message, Message):
        return
    current = await state.get_state()
    if current is None:
        await message.edit_text("Диалог устарел. Начните заново: /add")
        return
    data = await state.get_data()

    match callback_data.action:
        case "cancel":
            await state.clear()
            await message.edit_text("Отменено.")

        case "routine":
            try:
                routine = await RoutineService(session).get_owned(user, int(callback_data.value))
            except NotFoundError:
                await message.edit_text("Рутина не найдена. Начните заново: /add")
                await state.clear()
                return
            await state.update_data(routine_id=routine.id)
            await state.set_state(AddHabit.confirm)
            await message.edit_text(
                f"Добавить «{_title(data)}» в «{escape(with_emoji(routine.title, routine.emoji))}»"
                f" ({describe_rrule(routine.schedule_rrule)})?",
                reply_markup=add_confirm_keyboard("✅ Добавить"),
            )

        case "new":
            await state.set_state(AddHabit.routine_title)
            await message.edit_text(
                "Как назвать новую рутину? <i>Например: «🌙 Вечер»</i>",
                reply_markup=add_cancel_keyboard(),
            )

        case "preset" if current == AddHabit.preset.state:
            await state.update_data(preset=SchedulePreset(callback_data.value).value)
            await state.set_state(AddHabit.time)
            await message.edit_text("Во сколько?", reply_markup=add_time_keyboard())

        case "time" if current == AddHabit.time.state:
            value = callback_data.value
            await _ask_new_routine_confirm(
                message, state, int(value[:2]), int(value[2:]), new_message=False
            )

        case "custom_time" if current == AddHabit.time.state:
            await state.set_state(AddHabit.custom_time)
            await message.edit_text(
                "Напишите время в формате <code>ЧЧ:ММ</code>, например <code>07:45</code>",
                reply_markup=add_cancel_keyboard(),
            )

        case "confirm" if current == AddHabit.confirm.state:
            await _create(message, state, session, user, data)


async def _create(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    data: dict[str, Any],
) -> None:
    routines = RoutineService(session)
    if data.get("routine_id") is not None:
        routine = await routines.get_owned(user, data["routine_id"])
    else:
        routine = await routines.create(
            user, data["routine_title"], data["rrule"], emoji=data.get("routine_emoji")
        )
    await HabitService(session).create(routine, data["title"], emoji=data.get("emoji"))
    await state.clear()
    await message.edit_text(
        f"✅ Добавлено: «{_title(data)}» → «{escape(with_emoji(routine.title, routine.emoji))}», "
        f"{describe_rrule(routine.schedule_rrule)}.\n"
        "Привычка появится в чек-листе со следующего напоминания."
    )
