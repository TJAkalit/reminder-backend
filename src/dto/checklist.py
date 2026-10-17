"""Checklist view passed from services to the Telegram layer (not exposed by the HTTP API)."""

from datetime import date

from src.domain.enums import CheckStatus
from src.dto.base import Dto


class ChecklistItem(Dto):
    habit_id: int
    title: str
    emoji: str | None
    status: CheckStatus
    current_streak: int


class Checklist(Dto):
    occurrence_id: int
    chat_id: int
    message_id: int | None
    routine_title: str
    routine_emoji: str | None
    local_date: date
    is_open: bool
    items: list[ChecklistItem]

    @property
    def done_count(self) -> int:
        return sum(1 for item in self.items if item.status is CheckStatus.DONE)


class CheckResult(Dto):
    checklist: Checklist
    habit_title: str
    new_status: CheckStatus
    # Streak threshold reached by this check, e.g. 21.
    milestone: int | None
