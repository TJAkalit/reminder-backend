from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.texts import checklist_button, with_emoji
from src.domain.schedule import PRESET_TITLES_RU, SchedulePreset
from src.dto.checklist import Checklist
from src.model import Habit, Routine

TIME_CHOICES = ("06:00", "06:30", "07:00", "07:30", "08:00", "08:30", "09:00", "09:30")


class CheckCb(CallbackData, prefix="chk"):
    occurrence_id: int
    habit_id: int


class AddCb(CallbackData, prefix="add"):
    # routine | new | preset | time | custom_time | confirm | cancel
    action: str
    value: str = ""


class AccessCb(CallbackData, prefix="acc"):
    # allow | deny
    action: str
    chat_id: int


class ArchiveCb(CallbackData, prefix="arc"):
    # pick | yes | cancel
    action: str
    habit_id: int = 0


def checklist_keyboard(checklist: Checklist) -> InlineKeyboardMarkup | None:
    if not checklist.is_open:
        return None
    builder = InlineKeyboardBuilder()
    for item in checklist.items:
        builder.button(
            text=checklist_button(item),
            callback_data=CheckCb(occurrence_id=checklist.occurrence_id, habit_id=item.habit_id),
        )
    builder.adjust(1)
    return builder.as_markup()


def _cancel(builder: InlineKeyboardBuilder) -> None:
    builder.button(text="✖ Отмена", callback_data=AddCb(action="cancel"))


def add_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _cancel(builder)
    return builder.as_markup()


def add_routine_keyboard(routines: list[Routine]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for routine in routines:
        builder.button(
            text=with_emoji(routine.title, routine.emoji),
            callback_data=AddCb(action="routine", value=str(routine.id)),
        )
    builder.button(text="➕ Новая рутина", callback_data=AddCb(action="new"))
    _cancel(builder)
    builder.adjust(1)
    return builder.as_markup()


def add_preset_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for preset in SchedulePreset:
        builder.button(
            text=PRESET_TITLES_RU[preset], callback_data=AddCb(action="preset", value=preset.value)
        )
    _cancel(builder)
    builder.adjust(1)
    return builder.as_markup()


def add_time_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for choice in TIME_CHOICES:
        # ":" is the callback data separator, so the time travels as HHMM.
        builder.button(
            text=choice, callback_data=AddCb(action="time", value=choice.replace(":", ""))
        )
    builder.button(text="🕐 Другое время", callback_data=AddCb(action="custom_time"))
    _cancel(builder)
    builder.adjust(4, 4, 1, 1)
    return builder.as_markup()


def add_confirm_keyboard(label: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=label, callback_data=AddCb(action="confirm"))
    _cancel(builder)
    builder.adjust(2)
    return builder.as_markup()


def archive_pick_keyboard(habits: list[Habit]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for habit in habits:
        builder.button(
            text=with_emoji(habit.title, habit.emoji),
            callback_data=ArchiveCb(action="pick", habit_id=habit.id),
        )
    builder.button(text="✖ Отмена", callback_data=ArchiveCb(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def archive_confirm_keyboard(habit_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗄 В архив", callback_data=ArchiveCb(action="yes", habit_id=habit_id))
    builder.button(text="✖ Отмена", callback_data=ArchiveCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def access_request_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Разрешить", callback_data=AccessCb(action="allow", chat_id=chat_id))
    builder.button(text="⛔ Отклонить", callback_data=AccessCb(action="deny", chat_id=chat_id))
    builder.adjust(2)
    return builder.as_markup()
