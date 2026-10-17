"""User-facing Telegram texts (HTML parse mode)."""

from datetime import date
from html import escape

from src.domain.enums import CheckStatus
from src.dto.checklist import Checklist, ChecklistItem
from src.dto.habit import HabitOut
from src.dto.routine import RoutineOut
from src.model import ChatAccess

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

STATUS_MARK = {
    CheckStatus.PENDING: "⬜",
    CheckStatus.DONE: "✅",
    CheckStatus.SKIPPED: "⏭",
}

COMMANDS = {
    "today": "Чек-лист на сегодня",
    "habits": "Мои привычки и серии",
    "add": "Добавить привычку",
    "archive": "Убрать привычку в архив",
    "timezone": "Часовой пояс",
    "help": "Помощь",
}


ADMIN_COMMANDS = {
    "admin": "Администрирование",
    "users": "Кто имеет доступ",
    "requests": "Заявки на доступ",
    "allow": "Открыть доступ: /allow chat_id",
    "revoke": "Закрыть доступ: /revoke chat_id",
}


def access_line(entry: ChatAccess) -> str:
    crown = "👑 " if entry.is_admin else ""
    return f"{crown}{escape(entry.label)} — <code>{entry.telegram_chat_id}</code>"


def human_date(day: date) -> str:
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"


def with_emoji(title: str, emoji: str | None) -> str:
    return f"{emoji} {title}" if emoji else title


def checklist_button(item: ChecklistItem) -> str:
    label = f"{STATUS_MARK[item.status]} {with_emoji(item.title, item.emoji)}"
    if item.current_streak > 0:
        label += f" · 🔥{item.current_streak}"
    return label


def checklist_text(checklist: Checklist) -> str:
    header = (
        f"{checklist.routine_emoji or '🔔'} <b>{escape(checklist.routine_title)}</b>"
        f" · {human_date(checklist.local_date)}"
    )
    total = len(checklist.items)
    done = checklist.done_count
    if checklist.is_open:
        progress = (
            "Всё выполнено! 🎉" if total and done == total else f"Выполнено {done} из {total}"
        )
        return f"{header}\n{progress}\n\n<i>Нажимайте на привычку: ⬜ → ✅ → ⏭ (пропуск)</i>"
    lines = [
        f"{STATUS_MARK[item.status]} {escape(with_emoji(item.title, item.emoji))}"
        for item in checklist.items
    ]
    return f"{header}\nИтог: {done} из {total}\n\n" + "\n".join(lines)


def milestone_text(habit_title: str, threshold: int) -> str:
    return (
        f"🏆 <b>{threshold} {_days(threshold)} подряд!</b>\n«{escape(habit_title)}» — так держать!"
    )


def _days(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"


def help_text() -> str:
    commands = "\n".join(f"/{name} — {description}" for name, description in COMMANDS.items())
    return (
        "Я присылаю чек-листы привычек по расписанию. Отмечайте выполненное кнопками — "
        "до конца дня.\n\n" + commands
    )


def habits_text(routines: list[RoutineOut], habits: list[HabitOut]) -> str:
    if not habits:
        return "Привычек пока нет. Добавьте первую: /add"
    by_routine: dict[int, list[HabitOut]] = {}
    for habit in habits:
        by_routine.setdefault(habit.routine.id, []).append(habit)
    blocks: list[str] = []
    for routine in routines:
        items = by_routine.get(routine.id)
        if not items:
            continue
        lines = [
            f"{routine.emoji or '🔔'} <b>{escape(routine.title)}</b> — "
            f"{escape(routine.schedule.description)}"
        ]
        for habit in items:
            stats = habit.stats
            line = f"• {escape(with_emoji(habit.title, habit.emoji))} — 🔥 {stats.current_streak}"
            if stats.best_streak > stats.current_streak:
                line += f" (рекорд {stats.best_streak})"
            if stats.milestones:
                line += f" 🏅{max(m.threshold for m in stats.milestones)}"
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
