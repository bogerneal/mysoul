"""Map coordinates are optional: every county remains available in the table."""

import json
import math
from importlib.resources import files

from weather.dashboard import summarize
from weather.presentation import temperature


def load_points():
    return json.loads(
        files("weather").joinpath("fixtures/cwa_county_points_v1.json").read_text("utf-8")
    )


def valid_point(point):
    return point is not None and all(
        isinstance(point.get(key), (int, float))
        and not isinstance(point[key], bool)
        and math.isfinite(point[key])
        and low <= point[key] <= high
        for key, low, high in (("lat", -90, 90), ("lon", -180, 180))
    )


def map_rows(snapshot, day, cities, points):
    by_code = {p["code"]: p for p in points}
    by_name = {p["name"]: p for p in points}
    markers, table, missing = [], [], []
    for code, name in cities.items():
        summary = summarize(snapshot, code, day)
        row = {
            "code": code,
            "name": name,
            "low": temperature(summary.low),
            "high": temperature(summary.high),
            "coverage": "無預報"
            if not summary.periods
            else "部分時段"
            if summary.partial
            else "全天涵蓋",
        }
        table.append(row)
        point = by_name.get(name) if snapshot.mode == "demo" else by_code.get(code)
        if not valid_point(point) or point["name"] != name:
            missing.append(name)
            continue
        if not summary.periods:
            continue
        high = summary.high
        color = (
            [148, 163, 184]
            if high is None
            else [239, 108, 74]
            if high >= 30
            else [234, 179, 8]
            if high >= 25
            else [14, 165, 164]
            if high >= 20
            else [59, 130, 246]
        )
        markers.append({**point, **row, "color": color})
    return markers, table, missing
