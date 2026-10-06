import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from weather.geo import load_points, map_rows
from weather.live_parser import parse_live_forecast


@pytest.mark.parametrize("bad_lat", [None, "25", True, float("nan"), float("inf"), 91])
def test_invalid_coordinates_do_not_hide_forecasts(bad_lat):
    doc = json.loads(
        Path("tests/fixtures/cwa_weekly_20261004_evening.json").read_text(encoding="utf-8")
    )
    snapshot = parse_live_forecast(doc, fetched_at=datetime(2026, 10, 4, tzinfo=UTC))
    cities = {p.location_code: p.location_name for p in snapshot.periods}
    points = load_points()
    points[0]["lat"] = bad_lat
    markers, table, missing = map_rows(snapshot, date(2026, 10, 5), cities, points)
    assert len(markers) == 21
    assert len(table) == 22
    assert missing == [points[0]["name"]]
    assert {"金門縣", "澎湖縣"} <= {r["name"] for r in markers}
