from datetime import UTC, date, datetime, time

import pytest
from app.notifications.schedule import daily_slot, next_slot


@pytest.mark.parametrize(
    "day,clock,zone,expected",
    [
        ("2026-01-15", "19:00", "Europe/London", "2026-01-15T19:00:00+00:00"),
        ("2026-07-15", "19:00", "Europe/London", "2026-07-15T18:00:00+00:00"),
        ("2026-03-29", "01:30", "Europe/London", "2026-03-29T01:00:00+00:00"),
        ("2026-10-25", "01:30", "Europe/London", "2026-10-25T00:30:00+00:00"),
        ("2026-10-04", "02:15", "Australia/Lord_Howe", "2026-10-03T15:30:00+00:00"),
        ("2011-12-30", "19:00", "Pacific/Apia", "2011-12-30T10:00:00+00:00"),
    ],
)
def test_calendar_slots_handle_seasons_gaps_and_repeated_times(day, clock, zone, expected):
    slot = daily_slot(date.fromisoformat(day), time.fromisoformat(clock), zone)
    assert slot.local_date == date.fromisoformat(day)
    assert slot.at == datetime.fromisoformat(expected)


def test_repeated_hour_does_not_offer_second_occurrence():
    after = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    slot = next_slot(after, time(1, 30), "Europe/London")
    assert slot.local_date == date(2026, 10, 26)
    assert slot.at == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)


def test_restart_after_slot_waits_until_next_day_and_exact_cursor_advances():
    for hour in (19, 22):
        slot = next_slot(datetime(2026, 1, 15, hour, tzinfo=UTC), time(19), "Europe/London")
        assert slot.at == datetime(2026, 1, 16, 19, tzinfo=UTC)
    assert next_slot(
        datetime(2026, 1, 15, 18, tzinfo=UTC), time(19), "Europe/London"
    ).at == datetime(2026, 1, 15, 19, tzinfo=UTC)


def test_local_date_comes_from_owner_zone_and_naive_cursor_is_rejected():
    slot = next_slot(datetime(2026, 1, 15, 23, tzinfo=UTC), time(19), "Asia/Kolkata")
    assert slot.local_date == date(2026, 1, 16)
    assert slot.at == datetime(2026, 1, 16, 13, 30, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        next_slot(datetime(2026, 1, 15), time(19), "UTC")
