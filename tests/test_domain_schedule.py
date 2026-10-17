from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domain.schedule import (
    InvalidScheduleError,
    Schedule,
    SchedulePreset,
    describe_rrule,
    normalize_rrule,
    preset_rrule,
)

MSK = ZoneInfo("Europe/Moscow")
BERLIN = ZoneInfo("Europe/Berlin")


def test_daily_next_after_is_today_when_before_time() -> None:
    schedule = Schedule("FREQ=DAILY;BYHOUR=7;BYMINUTE=0", date(2026, 10, 1), MSK)
    # 03:00 UTC == 06:00 MSK
    assert schedule.next_after(datetime(2026, 10, 18, 3, 0, tzinfo=UTC)) == datetime(
        2026, 10, 18, 4, 0, tzinfo=UTC
    )


def test_daily_next_after_is_strictly_after() -> None:
    schedule = Schedule("FREQ=DAILY;BYHOUR=7;BYMINUTE=0", date(2026, 10, 1), MSK)
    run = datetime(2026, 10, 18, 4, 0, tzinfo=UTC)
    assert schedule.next_after(run) == datetime(2026, 10, 19, 4, 0, tzinfo=UTC)


def test_weekdays_skip_weekend() -> None:
    schedule = Schedule(preset_rrule(SchedulePreset.WEEKDAYS, 7, 0), date(2026, 10, 1), MSK)
    friday_after_run = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)
    assert schedule.next_after(friday_after_run) == datetime(2026, 10, 19, 4, 0, tzinfo=UTC)


def test_interval_is_anchored_to_start() -> None:
    schedule = Schedule("FREQ=DAILY;INTERVAL=3;BYHOUR=7;BYMINUTE=0", date(2026, 10, 1), MSK)
    assert schedule.runs_on(date(2026, 10, 4)) != []
    assert schedule.runs_on(date(2026, 10, 5)) == []
    assert schedule.runs_on(date(2026, 10, 7)) != []


def test_dst_keeps_local_time() -> None:
    # Berlin switches to winter time on 2026-10-25.
    schedule = Schedule("FREQ=DAILY;BYHOUR=7;BYMINUTE=0", date(2026, 10, 1), BERLIN)
    assert schedule.runs_on(date(2026, 10, 24)) == [datetime(2026, 10, 24, 5, 0, tzinfo=UTC)]
    assert schedule.runs_on(date(2026, 10, 26)) == [datetime(2026, 10, 26, 6, 0, tzinfo=UTC)]


def test_time_of_day() -> None:
    schedule = Schedule("FREQ=DAILY;BYHOUR=9;BYMINUTE=30", date(2026, 10, 1), MSK)
    assert schedule.time_of_day.isoformat(timespec="minutes") == "09:30"


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (
            "freq=weekly;byday=fr,mo;byminute=05;byhour=7",
            "FREQ=WEEKLY;BYDAY=MO,FR;BYHOUR=7;BYMINUTE=5",
        ),
        ("RRULE:FREQ=DAILY;BYHOUR=7;BYMINUTE=0", "FREQ=DAILY;BYHOUR=7;BYMINUTE=0"),
    ],
)
def test_normalize(rule: str, expected: str) -> None:
    assert normalize_rrule(rule) == expected


@pytest.mark.parametrize(
    "rule",
    [
        "FREQ=DAILY",  # no time
        "FREQ=HOURLY;BYHOUR=7;BYMINUTE=0",
        "FREQ=DAILY;BYHOUR=7,8;BYMINUTE=0",
        "FREQ=DAILY;BYHOUR=25;BYMINUTE=0",
        "FREQ=WEEKLY;BYDAY=XX;BYHOUR=7;BYMINUTE=0",
        "FREQ=DAILY;BYHOUR=7;BYMINUTE=0;DTSTART=20260101",
        "garbage",
    ],
)
def test_normalize_rejects(rule: str) -> None:
    with pytest.raises(InvalidScheduleError):
        normalize_rrule(rule)


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ("FREQ=DAILY;BYHOUR=7;BYMINUTE=0", "каждый день в 07:00"),
        ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;BYHOUR=7;BYMINUTE=0", "по будням в 07:00"),
        ("FREQ=WEEKLY;BYDAY=SA,SU;BYHOUR=9;BYMINUTE=30", "по выходным в 09:30"),
        ("FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=7;BYMINUTE=0", "по пн, ср, пт в 07:00"),
        ("FREQ=DAILY;INTERVAL=3;BYHOUR=7;BYMINUTE=0", "раз в 3 дня в 07:00"),
        ("FREQ=DAILY;INTERVAL=5;BYHOUR=7;BYMINUTE=0", "раз в 5 дней в 07:00"),
        ("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO;BYHOUR=7;BYMINUTE=0", "раз в 2 недели, по пн в 07:00"),
        ("FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=10;BYMINUTE=0", "1-го числа каждого месяца в 10:00"),
    ],
)
def test_describe(rule: str, expected: str) -> None:
    assert describe_rrule(rule) == expected
