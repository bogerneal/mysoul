"""Date queries shared by all dashboard views; no network or UI state."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from weather.models import ForecastPeriod, ForecastSnapshot
from weather.presentation import TAIPEI


@dataclass(frozen=True)
class DailyForecast:
    day: date
    low: float | None
    high: float | None
    partial: bool
    missing: bool
    periods: tuple[ForecastPeriod, ...]


def summarize(snapshot: ForecastSnapshot, code: str, day: date) -> DailyForecast:
    start = datetime.combine(day, time.min, TAIPEI)
    end = start + timedelta(days=1)
    periods = tuple(
        sorted(
            (
                p
                for p in snapshot.periods
                if p.location_code == code and p.start_at < end and p.end_at > start
            ),
            key=lambda p: p.start_at,
        )
    )
    lows = [p.min_temp_c for p in periods if p.min_temp_c is not None]
    highs = [p.max_temp_c for p in periods if p.max_temp_c is not None]
    cursor, gap = start, False
    for period in periods:
        left, right = max(start, period.start_at), min(end, period.end_at)
        gap |= left > cursor
        cursor = max(cursor, right)
    return DailyForecast(
        day,
        min(lows) if lows else None,
        max(highs) if highs else None,
        gap or cursor < end,
        any(p.min_temp_c is None or p.max_temp_c is None for p in periods),
        periods,
    )


def available_dates(snapshot: ForecastSnapshot, code: str, today: date) -> list[date]:
    days = set()
    for period in snapshot.periods:
        if period.location_code != code:
            continue
        day = period.start_at.astimezone(TAIPEI).date()
        last = (period.end_at - timedelta(microseconds=1)).astimezone(TAIPEI).date()
        while day <= last:
            if snapshot.mode == "demo" or day >= today:
                days.add(day)
            day += timedelta(days=1)
    return sorted(days)[:7]
