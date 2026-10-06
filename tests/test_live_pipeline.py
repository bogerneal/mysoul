import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from weather.cwa_client import CwaError
from weather.forecast_service import import_live, update_live
from weather.live_parser import COUNTIES, parse_live_forecast
from weather.parser import DATASET_ID, ContractError
from weather.pipeline_cli import main
from weather.presentation import summarize
from weather.repository import ForecastRepository

CAPTURED = datetime(2026, 10, 4, 7, 19, 9, 450480, tzinfo=UTC)


def test_evening_response_has_fifteen_periods_and_truncation_is_rejected():
    path = Path(__file__).parent / "fixtures/cwa_weekly_20261004_evening.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    data = parse_live_forecast(document, fetched_at=CAPTURED)
    assert len(data.periods) == 330
    assert max(p.end_at for p in data.periods) == datetime(2026, 10, 11, 22, tzinfo=UTC)
    for loc in locations(document):
        for e in loc["WeatherElement"]:
            e["Time"].pop()
    with pytest.raises(ContractError, match="incomplete_period_coverage"):
        parse_live_forecast(document, fetched_at=CAPTURED)


def test_old_forecast_cannot_replace_later_horizon_with_new_capture_time(tmp_path, real_document):
    from weather.repository import RepositoryError

    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    path = Path(__file__).parent / "fixtures/cwa_weekly_20261004_evening.json"
    newer = json.loads(path.read_text(encoding="utf-8"))
    first = repo.save(parse_live_forecast(newer, fetched_at=CAPTURED))
    with pytest.raises(RepositoryError, match="older_forecast_rejected"):
        repo.save(parse_live_forecast(real_document, fetched_at=CAPTURED + timedelta(hours=1)))
    assert repo.read(DATASET_ID, "live").batch_id == first


@pytest.fixture
def real_document():
    return json.loads(
        (Path(__file__).parent / "fixtures/cwa_weekly_20261004.json").read_text(encoding="utf-8")
    )


def locations(doc):
    return doc["records"]["Locations"][0]["Location"]


def element(loc, name="最低溫度"):
    return next(e for e in loc["WeatherElement"] if e["ElementName"] == name)


@pytest.fixture
def clock(monkeypatch):
    mocked = Mock()
    mocked.now.return_value = CAPTURED + timedelta(minutes=1)
    monkeypatch.setattr("weather.forecast_service.datetime", mocked)
    return mocked


@pytest.mark.parametrize(
    "filename,count,start,end",
    [
        ("cwa_weekly_20261004.json", 308, "2026-10-04T04:00:00+00:00", "2026-10-10T22:00:00+00:00"),
        (
            "cwa_weekly_20261004_evening.json",
            330,
            "2026-10-04T10:00:00+00:00",
            "2026-10-11T22:00:00+00:00",
        ),
        (
            "cwa_weekly_20261006_early.json",
            330,
            "2026-10-05T16:00:00+00:00",
            "2026-10-12T22:00:00+00:00",
        ),
    ],
)
def test_real_sample_matches_all_source_values(filename, count, start, end):
    real_document = json.loads(
        (Path(__file__).parent / "fixtures" / filename).read_text(encoding="utf-8")
    )
    data = parse_live_forecast(real_document, fetched_at=CAPTURED)
    assert len(data.periods) == count
    assert {p.location_code for p in data.periods} == set(COUNTIES)
    assert data.source_issued_at is None
    assert data.mode == "live"
    indexed = {(p.location_code, p.start_at, p.end_at): p for p in data.periods}
    for loc in locations(real_document):
        for label, key, attribute in [
            ("最低溫度", "MinTemperature", "min_temp_c"),
            ("最高溫度", "MaxTemperature", "max_temp_c"),
        ]:
            for row in element(loc, label)["Time"]:
                record = indexed[
                    (
                        loc["Geocode"],
                        datetime.fromisoformat(row["StartTime"]),
                        datetime.fromisoformat(row["EndTime"]),
                    )
                ]
                assert getattr(record, attribute) == float(row["ElementValue"][0][key])
    assert min(p.start_at for p in data.periods) == datetime.fromisoformat(start)
    assert max(p.end_at for p in data.periods) == datetime.fromisoformat(end)


def test_reordering_and_unrelated_factors_do_not_change_result(real_document):
    expected = parse_live_forecast(real_document, fetched_at=CAPTURED)
    locations(real_document).reverse()
    for loc in locations(real_document):
        loc["WeatherElement"].reverse()
        for e in loc["WeatherElement"]:
            e["Time"].reverse()
        loc["WeatherElement"].append({"ElementName": "12小時降雨機率", "Time": []})
    assert parse_live_forecast(real_document, fetched_at=CAPTURED) == expected


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda d: locations(d).pop(), "incomplete_county_coverage"),
        (lambda d: locations(d).append(deepcopy(locations(d)[0])), "duplicate_location"),
        (lambda d: locations(d)[0].update(Geocode="DEMO-TPE"), "unknown_location"),
        (lambda d: locations(d)[0].update(LocationName="臺北市"), "location_name_mismatch"),
        (lambda d: d["result"].update(resource_id="F-D0047-089"), "unexpected_dataset"),
        (lambda d: d.update(synthetic=True), "live_response_required"),
        (lambda d: element(locations(d)[0])["Time"].pop(), "unaligned_periods"),
        (lambda d: locations(d)[0]["WeatherElement"].pop(), "missing_temperature_element"),
    ],
)
def test_bad_contract_is_rejected(real_document, mutation, code):
    mutation(real_document)
    with pytest.raises(ContractError, match=f"^{code}$"):
        parse_live_forecast(real_document, fetched_at=CAPTURED)


@pytest.mark.parametrize("value", [None, "-", "-99", "NaN", True])
def test_unverified_missing_and_invalid_temperatures_reject(real_document, value):
    element(locations(real_document)[0])["Time"][0]["ElementValue"][0]["MinTemperature"] = value
    with pytest.raises(ContractError):
        parse_live_forecast(real_document, fetched_at=CAPTURED)


def test_truncated_all_counties_reject(real_document):
    for loc in locations(real_document):
        for e in loc["WeatherElement"]:
            e["Time"].pop()
    with pytest.raises(ContractError, match="incomplete_period_coverage"):
        parse_live_forecast(real_document, fetched_at=CAPTURED)


def test_gap_in_otherwise_complete_series_rejects(real_document):
    for e in locations(real_document)[0]["WeatherElement"]:
        e["Time"][1]["StartTime"] = "2026-10-04T19:00:00+08:00"
    with pytest.raises(ContractError, match="invalid_period_coverage"):
        parse_live_forecast(real_document, fetched_at=CAPTURED)


def test_import_preserves_capture_time_and_failure_retains_snapshot(tmp_path, real_document, clock):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    first = import_live(repo, real_document, fetched_at=CAPTURED)
    assert import_live(repo, real_document, fetched_at=CAPTURED) == first
    state = repo.read(DATASET_ID, "live", now=CAPTURED + timedelta(days=10))
    assert state.snapshot.fetched_at == CAPTURED
    assert datetime.fromisoformat(state.last_success_at) == CAPTURED
    assert state.stale
    locations(real_document).pop()
    with pytest.raises(ContractError):
        import_live(repo, real_document, fetched_at=CAPTURED)
    assert repo.read(DATASET_ID, "live").batch_id == first
    assert repo.read(DATASET_ID, "live").last_error_code == "update_failed"
    assert repo.read(DATASET_ID, "demo").snapshot is None


def test_update_network_failure_and_recovery(tmp_path, real_document, clock, monkeypatch):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    first = import_live(repo, real_document, fetched_at=CAPTURED)
    fetch = Mock(side_effect=CwaError("authorization_failed"))
    monkeypatch.setattr("weather.forecast_service.fetch_weekly", fetch)
    with pytest.raises(CwaError, match="authorization_failed"):
        update_live(repo, "test-only")
    assert repo.read(DATASET_ID, "live").batch_id == first
    assert repo.read(DATASET_ID, "live").last_error_code == "update_failed"
    fetch.side_effect = None
    fetch.return_value = real_document
    assert update_live(repo, "test-only") == first
    state = repo.read(DATASET_ID, "live")
    assert state.last_error_code is None
    assert datetime.fromisoformat(state.last_success_at) == clock.now.return_value


def test_expired_network_response_cannot_refresh_success(
    tmp_path, real_document, clock, monkeypatch
):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    first = import_live(repo, real_document, fetched_at=CAPTURED)
    clock.now.return_value = CAPTURED + timedelta(days=10)
    monkeypatch.setattr("weather.forecast_service.fetch_weekly", lambda key: real_document)
    with pytest.raises(ContractError, match="expired_live_response"):
        update_live(repo, "test-only")
    state = repo.read(DATASET_ID, "live")
    assert state.batch_id == first
    assert datetime.fromisoformat(state.last_success_at) == CAPTURED


def test_summary_is_local_time_and_exact_county(tmp_path, real_document, clock):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    import_live(repo, real_document, fetched_at=CAPTURED)
    state = repo.read(DATASET_ID, "live", now=CAPTURED)
    text = summarize(state, "live", "台北市")
    assert "CWA 真實預報" in text
    assert "2026-10-04 15:19" in text
    assert "臺北市 | 2026-10-04 12:00" in text
    assert "高雄市 |" not in text
    assert "找不到符合的縣市" in summarize(state, "live", "unknown")


def test_import_command_and_readable_status(tmp_path, real_document, clock, capsys):
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps(real_document), encoding="utf-8")
    db = str(tmp_path / "weather.sqlite3")
    assert (
        main(
            ["import-cwa", "--file", str(sample), "--fetched-at", CAPTURED.isoformat(), "--db", db]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["mode"] == "live"
    assert main(["status", "--mode", "live", "--summary", "--location", "臺北市", "--db", db]) == 0
    assert "臺北市 |" in capsys.readouterr().out
    assert main(["status", "--mode", "live", "--db", db]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["query_does_not_fetch"] is True
    assert len(result["snapshot"]["periods"]) == 308
