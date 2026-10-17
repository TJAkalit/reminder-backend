"""Routine schedules stored as RFC 5545 RRULE strings.

The rule is evaluated in the user's local wall-clock time: ``BYHOUR``/``BYMINUTE`` mean
"07:00 where the user lives". ``start`` is the local date the rule is anchored to
(it matters for ``INTERVAL`` > 1). All results are returned in UTC.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from dateutil import rrule as du_rrule

from src.domain.clock import local_to_utc

WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WEEKDAY_SHORT_RU = {
    "MO": "пн",
    "TU": "вт",
    "WE": "ср",
    "TH": "чт",
    "FR": "пт",
    "SA": "сб",
    "SU": "вс",
}
_ALLOWED_FREQ = {"DAILY", "WEEKLY", "MONTHLY"}
_ALLOWED_PARTS = {"FREQ", "INTERVAL", "BYDAY", "BYHOUR", "BYMINUTE", "BYMONTHDAY", "UNTIL", "COUNT"}


class SchedulePreset(StrEnum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"


PRESET_TITLES_RU = {
    SchedulePreset.DAILY: "Каждый день",
    SchedulePreset.WEEKDAYS: "По будням",
    SchedulePreset.WEEKENDS: "По выходным",
}


class InvalidScheduleError(ValueError):
    pass


def parse_parts(rule: str) -> dict[str, str]:
    rule = rule.strip().upper().removeprefix("RRULE:")
    parts: dict[str, str] = {}
    for chunk in rule.split(";"):
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        if not sep or not value:
            raise InvalidScheduleError(f"Malformed RRULE part: {chunk!r}")
        parts[key] = value
    return parts


def format_parts(parts: dict[str, str]) -> str:
    order = ["FREQ", "INTERVAL", "BYMONTHDAY", "BYDAY", "BYHOUR", "BYMINUTE", "COUNT", "UNTIL"]
    return ";".join(f"{key}={parts[key]}" for key in order if key in parts)


def normalize_rrule(rule: str) -> str:
    """Validate a rule and return its canonical form.

    Requirements: a supported FREQ and exactly one time of day (BYHOUR + BYMINUTE).
    """
    parts = parse_parts(rule)
    unknown = set(parts) - _ALLOWED_PARTS
    if unknown:
        raise InvalidScheduleError(f"Unsupported RRULE parts: {', '.join(sorted(unknown))}")
    if parts.get("FREQ") not in _ALLOWED_FREQ:
        raise InvalidScheduleError("FREQ must be one of DAILY, WEEKLY, MONTHLY")
    for key, upper in (("BYHOUR", 23), ("BYMINUTE", 59)):
        value = parts.get(key)
        if value is None or not value.isdigit() or not 0 <= int(value) <= upper:
            raise InvalidScheduleError(f"{key} must be a single number in 0..{upper}")
        parts[key] = str(int(value))
    if "INTERVAL" in parts and (not parts["INTERVAL"].isdigit() or int(parts["INTERVAL"]) < 1):
        raise InvalidScheduleError("INTERVAL must be a positive number")
    if "BYDAY" in parts:
        days = parts["BYDAY"].split(",")
        if not days or any(day not in WEEKDAYS for day in days):
            raise InvalidScheduleError("BYDAY must list days as MO,TU,...,SU")
        parts["BYDAY"] = ",".join(sorted(set(days), key=WEEKDAYS.index))
    normalized = format_parts(parts)
    try:
        du_rrule.rrulestr(normalized, dtstart=datetime(2000, 1, 1))
    except (ValueError, TypeError) as exc:
        raise InvalidScheduleError(str(exc)) from exc
    return normalized


def preset_rrule(preset: SchedulePreset, hour: int, minute: int) -> str:
    match preset:
        case SchedulePreset.DAILY:
            rule = "FREQ=DAILY"
        case SchedulePreset.WEEKDAYS:
            rule = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        case SchedulePreset.WEEKENDS:
            rule = "FREQ=WEEKLY;BYDAY=SA,SU"
    return normalize_rrule(f"{rule};BYHOUR={hour};BYMINUTE={minute}")


@dataclass(frozen=True, slots=True)
class Schedule:
    rrule: str
    start: date
    tz: ZoneInfo

    def _rule(self) -> du_rrule.rrule:
        rule = du_rrule.rrulestr(self.rrule, dtstart=datetime.combine(self.start, time.min))
        assert isinstance(rule, du_rrule.rrule)
        return rule

    def next_after(self, after: datetime) -> datetime | None:
        """First run strictly after ``after`` (aware), in UTC; None if the rule is exhausted."""
        local_after = after.astimezone(self.tz).replace(tzinfo=None)
        found = self._rule().after(local_after, inc=False)
        return local_to_utc(found, self.tz) if found else None

    def runs_on(self, day: date) -> list[datetime]:
        """All runs on a local date, in UTC."""
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        return [
            local_to_utc(found, self.tz)
            for found in self._rule().between(start, end, inc=True)
            if found < end
        ]

    @property
    def time_of_day(self) -> time:
        parts = parse_parts(self.rrule)
        return time(int(parts["BYHOUR"]), int(parts["BYMINUTE"]))


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _describe_days(days: list[str]) -> str:
    if len(days) == 7:
        return "каждый день"
    if days == ["MO", "TU", "WE", "TH", "FR"]:
        return "по будням"
    if days == ["SA", "SU"]:
        return "по выходным"
    return "по " + ", ".join(WEEKDAY_SHORT_RU[day] for day in days)


def describe_rrule(rule: str) -> str:
    """Human-readable Russian description, e.g. «по будням в 07:00»."""
    try:
        parts = parse_parts(normalize_rrule(rule))
    except InvalidScheduleError:
        return rule
    at = f"в {int(parts['BYHOUR']):02d}:{int(parts['BYMINUTE']):02d}"
    interval = int(parts.get("INTERVAL", "1"))
    days = parts["BYDAY"].split(",") if "BYDAY" in parts else None

    match parts["FREQ"]:
        case "DAILY" if days:
            when = _describe_days(days)
        case "DAILY":
            when = (
                "каждый день"
                if interval == 1
                else f"раз в {interval} {_plural_ru(interval, 'день', 'дня', 'дней')}"
            )
        case "WEEKLY":
            when = _describe_days(days) if days else "раз в неделю"
            if interval > 1:
                weeks = _plural_ru(interval, "неделю", "недели", "недель")
                when = f"раз в {interval} {weeks}, {when.removeprefix('раз в неделю')}".rstrip(", ")
        case "MONTHLY" if "BYMONTHDAY" in parts:
            when = f"{parts['BYMONTHDAY']}-го числа"
            when += (
                " каждого месяца"
                if interval == 1
                else f" раз в {interval} {_plural_ru(interval, 'месяц', 'месяца', 'месяцев')}"
            )
        case "MONTHLY":
            when = "раз в месяц"
        case _:
            return rule
    return f"{when} {at}"
