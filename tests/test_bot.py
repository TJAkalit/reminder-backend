from datetime import date, time

import pytest
from aiogram import Bot

from src.bot.factory import create_dispatcher
from src.bot.keyboards import AddCb, CheckCb, checklist_keyboard
from src.bot.notifier import TelegramNotifier
from src.bot.parsing import parse_time, split_emoji
from src.bot.texts import checklist_text, milestone_text
from src.config import Settings
from src.domain.enums import CheckStatus
from src.dto.checklist import Checklist, ChecklistItem


def make_checklist(*, is_open: bool = True) -> Checklist:
    return Checklist(
        occurrence_id=5,
        chat_id=111,
        message_id=None,
        routine_title="Утро",
        routine_emoji="🌅",
        local_date=date(2026, 10, 18),
        is_open=is_open,
        items=[
            ChecklistItem(
                habit_id=1, title="Вода", emoji="💧", status=CheckStatus.DONE, current_streak=3
            ),
            ChecklistItem(
                habit_id=2,
                title="Зарядка <10 мин>",
                emoji=None,
                status=CheckStatus.PENDING,
                current_streak=0,
            ),
        ],
    )


def test_open_checklist_rendering() -> None:
    checklist = make_checklist()
    text = checklist_text(checklist)
    assert "🌅 <b>Утро</b> · 18 октября" in text
    assert "Выполнено 1 из 2" in text

    markup = checklist_keyboard(checklist)
    assert markup is not None
    labels = [row[0].text for row in markup.inline_keyboard]
    assert labels == ["✅ 💧 Вода · 🔥3", "⬜ Зарядка <10 мин>"]
    data = markup.inline_keyboard[0][0].callback_data
    assert data is not None
    assert CheckCb.unpack(data) == CheckCb(occurrence_id=5, habit_id=1)


def test_closed_checklist_has_summary_and_no_buttons() -> None:
    checklist = make_checklist(is_open=False)
    text = checklist_text(checklist)
    assert "Итог: 1 из 2" in text
    assert "⬜ Зарядка &lt;10 мин&gt;" in text  # escaped for HTML
    assert checklist_keyboard(checklist) is None


def test_milestone_text_plural() -> None:
    assert "21 день подряд" in milestone_text("Вода", 21)
    assert "14 дней подряд" in milestone_text("Вода", 14)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("💧 Стакан воды", ("💧", "Стакан воды")),
        ("Стакан воды", (None, "Стакан воды")),
        ("  🌅   Утро ", ("🌅", "Утро")),
        ("💧", (None, "💧")),
    ],
)
def test_split_emoji(text: str, expected: tuple[str | None, str]) -> None:
    assert split_emoji(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("07:45", time(7, 45)), ("7.05", time(7, 5)), ("0745", time(7, 45)), ("25:00", None)],
)
def test_parse_time(text: str, expected: time | None) -> None:
    assert parse_time(text) == expected


def test_callback_data_fits_telegram_limit() -> None:
    assert len(CheckCb(occurrence_id=10**9, habit_id=10**9).pack()) <= 64
    assert len(AddCb(action="custom_time", value="1234567890").pack()) <= 64


def test_dispatcher_builds(session_factory) -> None:
    bot = Bot("123456:TEST-TOKEN")
    dp = create_dispatcher(Settings(), session_factory, TelegramNotifier(bot))
    assert {"message", "callback_query"} <= set(dp.resolve_used_update_types())
