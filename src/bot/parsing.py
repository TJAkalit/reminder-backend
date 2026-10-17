"""Parsing of free-text user input in bot dialogs."""

import re
from datetime import time

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.\s]?(\d{2})\s*$")


def split_emoji(text: str) -> tuple[str | None, str]:
    """«💧 Стакан воды» → ("💧", "Стакан воды"); text without a leading emoji is kept as is."""
    text = " ".join(text.split())
    head, _, rest = text.partition(" ")
    if rest and len(head) <= 8 and not any(ch.isalnum() for ch in head):
        return head, rest
    return None, text


def parse_time(text: str) -> time | None:
    match = _TIME_RE.match(text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)
