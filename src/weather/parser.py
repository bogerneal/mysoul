"""Strict synthetic fixture parser, NOT a verified live CWA adapter.

Official field names inform the candidate payload. The envelope, null convention,
element names, array layout and DEMO codes remain a project-owned test contract.
"""

import math
from datetime import UTC, datetime

from weather.models import ForecastPeriod, ForecastSnapshot

SCHEMA_VERSION = "mysoul.synthetic-weekly.v1"
DATASET_ID = "F-D0047-091"
DEMO_LOCATIONS = {"DEMO-TPE": "臺北市", "DEMO-KHH": "高雄市"}
ELEMENTS = {"最低溫度": "MinTemperature", "最高溫度": "MaxTemperature"}


class ContractError(ValueError):
    """A safe contract error: codes only, never raw input or credentials."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _object(value: object) -> dict:
    if not isinstance(value, dict):
        raise ContractError("expected_object")
    return value


def _array(value: object) -> list:
    if not isinstance(value, list) or not value:
        raise ContractError("expected_nonempty_array")
    return value


def _required(obj: dict, key: str) -> object:
    if key not in obj:
        raise ContractError("missing_field")
    return obj[key]


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ContractError("invalid_timestamp")
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ContractError("timezone_required")
        return result.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("invalid_timestamp") from None


def _temperature(value: object) -> float | None:
    # Only JSON null represents missing data in v1. No guessed CWA sentinel codes.
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ContractError("invalid_temperature")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ContractError("invalid_temperature") from None
    if not math.isfinite(result):
        raise ContractError("invalid_temperature")
    # Project guardrail, not a CWA specification; rejects sentinel-like -99/-999.
    if not -80 <= result <= 65:
        raise ContractError("temperature_out_of_range")
    return result


def _series(element: dict, value_key: str) -> dict[tuple[datetime, datetime], float | None]:
    result = {}
    for item in _array(_required(element, "Time")):
        item = _object(item)
        start = _timestamp(_required(item, "StartTime"))
        end = _timestamp(_required(item, "EndTime"))
        if end <= start:
            raise ContractError("invalid_period")
        key = (start, end)
        if key in result:
            raise ContractError("duplicate_period")
        values = _array(_required(item, "ElementValue"))
        if len(values) != 1:
            raise ContractError("ambiguous_element_value")
        result[key] = _temperature(_required(_object(values[0]), value_key))
    intervals = sorted(result)
    if any(
        current[0] < previous[1]
        for previous, current in zip(intervals, intervals[1:], strict=False)
    ):
        raise ContractError("overlapping_periods")
    return result


def parse_demo_forecast(document: object, *, fetched_at: datetime) -> ForecastSnapshot:
    """Validate v1 synthetic data and align min/max by location and UTC interval.

    Live CWA responses are intentionally rejected here; use parse_live_forecast
    for the separately versioned live contract.
    """
    doc = _object(document)
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("unsupported_schema")
    if doc.get("synthetic") is not True or doc.get("mode") != "demo":
        raise ContractError("synthetic_demo_required")
    if doc.get("dataset_id") != DATASET_ID:
        raise ContractError("unexpected_dataset")
    if doc.get("temperature_unit") != "C":
        raise ContractError("unsupported_unit")
    if not isinstance(fetched_at, datetime) or fetched_at.utcoffset() is None:
        raise ContractError("fetched_at_timezone_required")
    issued_raw = _required(doc, "source_issued_at")
    issued = None if issued_raw is None else _timestamp(issued_raw)
    records = _object(_required(_object(_required(doc, "payload")), "records"))
    periods = []
    seen = set()
    for group in _array(_required(records, "Locations")):
        for location in _array(_required(_object(group), "Location")):
            location = _object(location)
            code = _required(location, "Geocode")
            name = _required(location, "LocationName")
            if not isinstance(code, str) or code not in DEMO_LOCATIONS:
                raise ContractError("unknown_location")
            if name != DEMO_LOCATIONS[code]:
                raise ContractError("location_name_mismatch")
            if code in seen:
                raise ContractError("duplicate_location")
            seen.add(code)
            elements = {}
            for element in _array(_required(location, "WeatherElement")):
                element = _object(element)
                label = _required(element, "ElementName")
                if not isinstance(label, str) or label not in ELEMENTS:
                    raise ContractError("unsupported_element")
                if label in elements:
                    raise ContractError("duplicate_element")
                elements[label] = _series(element, ELEMENTS[label])
            if set(elements) != set(ELEMENTS):
                raise ContractError("missing_temperature_element")
            minima, maxima = elements["最低溫度"], elements["最高溫度"]
            if minima.keys() != maxima.keys():
                raise ContractError("unaligned_periods")
            for (start, end), minimum in minima.items():
                maximum = maxima[(start, end)]
                if minimum is not None and maximum is not None and minimum > maximum:
                    raise ContractError("minimum_exceeds_maximum")
                flags = []
                if minimum is None:
                    flags.append("missing_min_temperature")
                if maximum is None:
                    flags.append("missing_max_temperature")
                if issued is None:
                    flags.append("missing_source_issued_at")
                periods.append(
                    ForecastPeriod(code, name, start, end, minimum, maximum, tuple(flags))
                )
    if not any(p.min_temp_c is not None or p.max_temp_c is not None for p in periods):
        raise ContractError("no_valid_temperatures")
    return ForecastSnapshot(
        dataset_id=DATASET_ID,
        mode="demo",
        source_issued_at=issued,
        fetched_at=fetched_at.astimezone(UTC),
        periods=tuple(sorted(periods, key=lambda p: (p.location_code, p.start_at, p.end_at))),
    )
