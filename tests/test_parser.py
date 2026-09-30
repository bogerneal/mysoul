from copy import deepcopy
from datetime import UTC, datetime

import pytest

from weather.parser import ContractError, parse_demo_forecast

FETCHED = datetime(2026, 12, 31, 9, tzinfo=UTC)


def locations(document):
    return document["payload"]["records"]["Locations"][0]["Location"]


def series(document, label="最低溫度"):
    return next(
        item["Time"]
        for item in locations(document)[0]["WeatherElement"]
        if item["ElementName"] == label
    )


def parse(document):
    return parse_demo_forecast(document, fetched_at=FETCHED)


def test_aligns_by_period_not_array_order_and_normalizes_cross_year(document):
    snapshot = parse(document)
    taipei = [p for p in snapshot.periods if p.location_code == "DEMO-TPE"]
    assert [(p.min_temp_c, p.max_temp_c) for p in taipei] == [(18, 22), (20, 26)]
    assert taipei[0].start_at == datetime(2026, 12, 31, 10, tzinfo=UTC)
    assert taipei[0].end_at == datetime(2026, 12, 31, 22, tzinfo=UTC)
    assert taipei[1].end_at == datetime(2027, 1, 1, 10, tzinfo=UTC)
    assert snapshot.mode == "demo"
    assert snapshot.fetched_at == FETCHED
    assert snapshot.source_issued_at is None
    assert len(snapshot.periods) == 4


def test_null_is_preserved_with_quality_flags(document):
    period = next(p for p in parse(document).periods if p.location_code == "DEMO-KHH")
    assert period.min_temp_c is None
    assert period.max_temp_c == 25
    assert period.quality_flags == ("missing_min_temperature", "missing_source_issued_at")


def test_input_is_not_mutated_and_order_does_not_change_result(document):
    original = deepcopy(document)
    expected = parse(document)
    assert document == original
    locations(document).reverse()
    for location in locations(document):
        location["WeatherElement"].reverse()
        for element in location["WeatherElement"]:
            element["Time"].reverse()
    assert parse(document) == expected


def test_equivalent_timezones_match_the_same_interval(document):
    row = series(document, "最高溫度")[1]
    row["StartTime"] = "2026-12-31T10:00:00Z"
    row["EndTime"] = "2026-12-31T22:00:00Z"
    assert len(parse(document).periods) == 4


def test_source_issue_time_is_distinct_from_fetch_time(document):
    document["source_issued_at"] = "2026-12-31T16:00:00+08:00"
    snapshot = parse(document)
    assert snapshot.source_issued_at == datetime(2026, 12, 31, 8, tzinfo=UTC)
    assert snapshot.source_issued_at != snapshot.fetched_at
    assert all("missing_source_issued_at" not in p.quality_flags for p in snapshot.periods)


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("schema_version", "v2", "unsupported_schema"),
        ("synthetic", False, "synthetic_demo_required"),
        ("synthetic", 1, "synthetic_demo_required"),
        ("mode", "live", "synthetic_demo_required"),
        ("dataset_id", "other", "unexpected_dataset"),
        ("temperature_unit", "F", "unsupported_unit"),
    ],
)
def test_rejects_unknown_contract_or_non_demo_input(document, field, value, code):
    document[field] = value
    with pytest.raises(ContractError, match=f"^{code}$"):
        parse(document)


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "", "secret-value", {}, []])
def test_invalid_temperatures_fail_without_echoing_input(document, value):
    series(document)[0]["ElementValue"][0]["MinTemperature"] = value
    with pytest.raises(ContractError, match="^invalid_temperature$"):
        parse(document)


@pytest.mark.parametrize("value", [-99, -999, 66])
def test_does_not_guess_missing_value_sentinels(document, value):
    series(document)[0]["ElementValue"][0]["MinTemperature"] = value
    with pytest.raises(ContractError, match="^temperature_out_of_range$"):
        parse(document)


def test_zero_is_a_valid_temperature(document):
    series(document)[0]["ElementValue"][0]["MinTemperature"] = "0"
    period = next(p for p in parse(document).periods if p.location_code == "DEMO-TPE")
    assert period.min_temp_c == 0
    assert "missing_min_temperature" not in period.quality_flags


@pytest.mark.parametrize(
    ("value", "code"),
    [("2026-12-31T18:00:00", "timezone_required"), ("invalid", "invalid_timestamp")],
)
def test_rejects_ambiguous_or_invalid_time(document, value, code):
    series(document)[0]["StartTime"] = value
    with pytest.raises(ContractError, match=f"^{code}$"):
        parse(document)


def test_rejects_naive_fetch_time(document):
    with pytest.raises(ContractError, match="fetched_at_timezone_required"):
        parse_demo_forecast(document, fetched_at=datetime(2026, 12, 31))


def test_rejects_reversed_interval(document):
    series(document)[0]["EndTime"] = series(document)[0]["StartTime"]
    with pytest.raises(ContractError, match="^invalid_period$"):
        parse(document)


def test_rejects_min_above_max(document):
    series(document)[0]["ElementValue"][0]["MinTemperature"] = "30"
    with pytest.raises(ContractError, match="^minimum_exceeds_maximum$"):
        parse(document)


def test_rejects_duplicate_period(document):
    series(document).append(deepcopy(series(document)[0]))
    with pytest.raises(ContractError, match="^duplicate_period$"):
        parse(document)


def test_rejects_overlapping_periods(document):
    series(document)[1]["StartTime"] = "2027-01-01T05:00:00+08:00"
    with pytest.raises(ContractError, match="^overlapping_periods$"):
        parse(document)


def test_rejects_unaligned_temperature_periods(document):
    series(document).pop()
    with pytest.raises(ContractError, match="^unaligned_periods$"):
        parse(document)


def test_rejects_missing_field_instead_of_treating_as_null(document):
    del series(document)[0]["ElementValue"][0]["MinTemperature"]
    with pytest.raises(ContractError, match="^missing_field$"):
        parse(document)


def test_rejects_missing_element(document):
    locations(document)[0]["WeatherElement"].pop()
    with pytest.raises(ContractError, match="^missing_temperature_element$"):
        parse(document)


def test_rejects_duplicate_element(document):
    elements = locations(document)[0]["WeatherElement"]
    elements.append(deepcopy(elements[0]))
    with pytest.raises(ContractError, match="^duplicate_element$"):
        parse(document)


def test_rejects_unknown_element(document):
    locations(document)[0]["WeatherElement"][0]["ElementName"] = "MinT"
    with pytest.raises(ContractError, match="^unsupported_element$"):
        parse(document)


@pytest.mark.parametrize("value", ["UNKNOWN", None, ["DEMO-TPE"]])
def test_rejects_unknown_location(document, value):
    locations(document)[0]["Geocode"] = value
    with pytest.raises(ContractError, match="^unknown_location$"):
        parse(document)


def test_rejects_location_name_mismatch(document):
    locations(document)[0]["LocationName"] = "高雄市"
    with pytest.raises(ContractError, match="^location_name_mismatch$"):
        parse(document)


def test_rejects_duplicate_location(document):
    locations(document).append(deepcopy(locations(document)[0]))
    with pytest.raises(ContractError, match="^duplicate_location$"):
        parse(document)


@pytest.mark.parametrize("value", [[], {}, None])
def test_rejects_empty_or_wrong_container(document, value):
    document["payload"]["records"]["Locations"] = value
    with pytest.raises(ContractError, match="^expected_nonempty_array$"):
        parse(document)


def test_rejects_entirely_missing_temperatures(document):
    for location in locations(document):
        for element in location["WeatherElement"]:
            for row in element["Time"]:
                row["ElementValue"][0] = dict.fromkeys(row["ElementValue"][0])
    with pytest.raises(ContractError, match="^no_valid_temperatures$"):
        parse(document)


def test_raw_live_response_is_not_accepted_as_demo(document):
    with pytest.raises(ContractError, match="^unsupported_schema$"):
        parse(document["payload"])
