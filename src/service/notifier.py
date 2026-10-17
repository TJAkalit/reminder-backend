from typing import Protocol

from src.dto.checklist import Checklist


class ChecklistNotifier(Protocol):
    """Port to the messenger. Implemented by the Telegram bot; faked in tests."""

    async def send_checklist(self, checklist: Checklist) -> int:
        """Send a new checklist message and return its message id."""
        ...

    async def update_checklist(self, checklist: Checklist) -> None:
        """Re-render an existing checklist message (``checklist.message_id``)."""
        ...

    async def close_checklist(self, checklist: Checklist) -> None:
        """Render the final state of a closed checklist and remove its buttons."""
        ...

    async def remove_buttons(self, chat_id: int, message_id: int) -> None:
        """Detach an outdated message (e.g. after the checklist was re-sent)."""
        ...
