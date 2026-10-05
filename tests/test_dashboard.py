from datetime import UTC, date, datetime

import pytest

from weather.dashboard import available_dates, summarize
from weather.models import ForecastPeriod, ForecastSnapshot
from weather.parser import DATASET_ID


def snapshot(*periods, mode="demo"):
    return ForecastSnapshot(DATASET_ID, mode, None, datetime.now(UTC), tuple(periods))


def period(start, end, low=18, high=25):
    return ForecastPeriod(
        "A", "City", datetime.fromisoformat(start), datetime.fromisoformat(end), low, high, ()
    )


def test_taipei_cross_year_and_midnight_exclusive():
    data = snapshot(period("2026-12-31T10:00:00+00:00", "2027-01-01T00:00:00+08:00"))
    assert available_dates(data, "A", date(2030, 1, 1)) == [date(2026, 12, 31)]
    assert summarize(data, "A", date(2026, 12, 31)).partial
    assert not summarize(data, "A", date(2027, 1, 1)).periods


def test_cross_midnight_contributes_to_both_days():
    data = snapshot(period("2026-12-31T18:00:00+08:00", "2027-01-01T06:00:00+08:00"))
    assert available_dates(data, "A", date(2026, 1, 1)) == [date(2026, 12, 31), date(2027, 1, 1)]
    assert summarize(data, "A", date(2027, 1, 1)).low == 18


@pytest.mark.parametrize("second_start,partial", [("12:00", False), ("13:00", True)])
def test_coverage_gaps_and_missing_values(second_start, partial):
    data = snapshot(
        period("2026-10-05T00:00:00+08:00", "2026-10-05T12:00:00+08:00", None, 28),
        period(f"2026-10-05T{second_start}:00+08:00", "2026-10-06T00:00:00+08:00", None, 30),
    )
    result = summarize(data, "A", date(2026, 10, 5))
    assert result.low is None
    assert result.high == 30
    assert result.missing
    assert result.partial is partial


def test_live_excludes_past_and_caps_seven_days():
    data = snapshot(period("2026-10-01T00:00:00+08:00", "2026-10-15T00:00:00+08:00"), mode="live")
    assert available_dates(data, "A", date(2026, 10, 5)) == [
        date(2026, 10, d) for d in range(5, 12)
    ]
    assert available_dates(data, "unknown", date(2026, 10, 5)) == []
