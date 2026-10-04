"""CWA F-D0047-091 adapter verified against the 2026-10-04 datastore sample.

Unknown missing-temperature sentinels fail closed; no guessing from rain fields.
"""

import json
from datetime import UTC, datetime, timedelta
from importlib.resources import files

from weather.models import ForecastPeriod, ForecastSnapshot
from weather.parser import (
    DATASET_ID,
    ELEMENTS,
    ContractError,
    _array,
    _object,
    _required,
    _series,
)

COUNTIES = json.loads(
    files("weather").joinpath("fixtures/cwa_counties_v1.json").read_text(encoding="utf-8")
)


def parse_live_forecast(document: object, *, fetched_at: datetime) -> ForecastSnapshot:
    doc = _object(document)
    if doc.get("synthetic") or "schema_version" in doc or "mode" in doc:
        raise ContractError("live_response_required")
    success = doc.get("success")
    if success is not True and success != "true":
        raise ContractError("api_rejected")
    if _object(_required(doc, "result")).get("resource_id") != DATASET_ID:
        raise ContractError("unexpected_dataset")
    if not isinstance(fetched_at, datetime) or fetched_at.utcoffset() is None:
        raise ContractError("fetched_at_timezone_required")
    groups = _array(_required(_object(_required(doc, "records")), "Locations"))
    if len(groups) != 1 or _object(groups[0]).get("Dataid") != "D0047-091":
        raise ContractError("unexpected_dataset")
    seen = set()
    periods = []
    expected_intervals = None
    for location in _array(_required(groups[0], "Location")):
        loc = _object(location)
        code, name = _required(loc, "Geocode"), _required(loc, "LocationName")
        if not isinstance(code, str) or code not in COUNTIES:
            raise ContractError("unknown_location")
        if name != COUNTIES[code]:
            raise ContractError("location_name_mismatch")
        if code in seen:
            raise ContractError("duplicate_location")
        seen.add(code)
        elements = {}
        for element in _array(_required(loc, "WeatherElement")):
            element = _object(element)
            label = _required(element, "ElementName")
            if not isinstance(label, str):
                raise ContractError("invalid_element_name")
            if label not in ELEMENTS:
                continue  # Other CWA factors are outside this adapter's contract.
            if label in elements:
                raise ContractError("duplicate_element")
            elements[label] = _series(element, ELEMENTS[label])
        if set(elements) != set(ELEMENTS):
            raise ContractError("missing_temperature_element")
        minima, maxima = elements["最低溫度"], elements["最高溫度"]
        if minima.keys() != maxima.keys():
            raise ContractError("unaligned_periods")
        intervals = sorted(minima)
        # Empirical guard for this dataset version; re-review schema if CWA changes it.
        if len(intervals) not in {14, 15}:
            raise ContractError("incomplete_period_coverage")
        # Both captured CWA editions end at 06:00 Taiwan time (22:00 UTC).
        # This also rejects an evening batch with its final 12-hour period removed.
        if intervals[-1][1].timetz().replace(tzinfo=None).isoformat() != "22:00:00":
            raise ContractError("incomplete_period_coverage")
        for index, (start, end) in enumerate(intervals):
            duration = end - start
            if (index == 0 and not timedelta(0) < duration <= timedelta(hours=12)) or (
                index > 0 and (duration != timedelta(hours=12) or start != intervals[index - 1][1])
            ):
                raise ContractError("invalid_period_coverage")
        if expected_intervals is not None and intervals != expected_intervals:
            raise ContractError("inconsistent_county_coverage")
        expected_intervals = intervals
        for start, end in intervals:
            low, high = minima[(start, end)], maxima[(start, end)]
            if low is None or high is None:
                raise ContractError("unverified_missing_temperature")
            if low > high:
                raise ContractError("minimum_exceeds_maximum")
            periods.append(
                ForecastPeriod(code, name, start, end, low, high, ("missing_source_issued_at",))
            )
    if seen != set(COUNTIES):
        raise ContractError("incomplete_county_coverage")
    # Datastore response has no verified issue timestamp. Never infer it from start time.
    return ForecastSnapshot(
        DATASET_ID,
        "live",
        None,
        fetched_at.astimezone(UTC),
        tuple(sorted(periods, key=lambda p: (p.location_code, p.start_at))),
    )
