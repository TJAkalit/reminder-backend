from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now_utc() -> datetime:
    return datetime.now(UTC)


def get_zone(name: str) -> ZoneInfo:
    """Return the IANA zone or raise ValueError for an unknown name."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def is_valid_timezone(name: str) -> bool:
    try:
        get_zone(name)
    except ValueError:
        return False
    return True


def to_local(moment: datetime, tz: ZoneInfo) -> datetime:
    return moment.astimezone(tz)


def local_date(moment: datetime, tz: ZoneInfo) -> date:
    return moment.astimezone(tz).date()


def local_to_utc(local: datetime, tz: ZoneInfo) -> datetime:
    """Interpret a naive local wall-clock time in ``tz`` and convert it to UTC."""
    return local.replace(tzinfo=tz).astimezone(UTC)


def day_start_utc(day: date, tz: ZoneInfo) -> datetime:
    return local_to_utc(datetime.combine(day, time.min), tz)


def day_end_utc(day: date, tz: ZoneInfo) -> datetime:
    """The first instant of the next local day — the moment ``day`` closes."""
    return day_start_utc(day + timedelta(days=1), tz)
