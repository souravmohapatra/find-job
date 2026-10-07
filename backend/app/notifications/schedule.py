"""Calendar-based digest slots, independent of collection intervals and host timezone."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Slot:
    local_date: date
    at: datetime


def candidates(local: datetime, zone: ZoneInfo) -> list[datetime]:
    """Round-tripping excludes imaginary times; sorting chooses the first fold."""
    return sorted(
        {
            instant
            for fold in (0, 1)
            if (instant := local.replace(tzinfo=zone, fold=fold).astimezone(UTC))
            .astimezone(zone)
            .replace(tzinfo=None)
            == local
        }
    )


def daily_slot(day: date, local_time: time, timezone: str) -> Slot:
    if local_time.tzinfo is not None or local_time.second or local_time.microsecond:
        raise ValueError("Use a local wall-clock time with minute precision.")
    zone = ZoneInfo(timezone)
    local = datetime.combine(day, local_time)
    # Includes half-hour DST gaps and whole skipped calendar dates. Settings are
    # minute-granular; no fixed one-hour transition assumption is made.
    for minutes in range(48 * 60 + 1):
        valid = candidates(local + timedelta(minutes=minutes), zone)
        if valid:
            return Slot(local_date=day, at=valid[0])
    raise ValueError("No valid digest slot within two days of the requested time.")


def next_slot(after: datetime, local_time: time, timezone: str) -> Slot:
    """Return the next future slot, never an off-schedule downtime catch-up."""
    if after.tzinfo is None or after.utcoffset() is None:
        raise ValueError("The scheduling cursor must be timezone-aware.")
    instant = after.astimezone(UTC)
    day = instant.astimezone(ZoneInfo(timezone)).date()
    for offset in range(3):
        slot = daily_slot(day + timedelta(days=offset), local_time, timezone)
        if slot.at > instant:
            return slot
    raise ValueError("No future digest slot found.")
