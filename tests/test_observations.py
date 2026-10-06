import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from weather import observations, ui
from weather.cwa_client import CwaError
from weather.map_layers import border_layer, boundaries, label_layer, map_style
from weather.observation_ui import map_rows, representative_labels
from weather.observations import ObservationStore, fresh_rows, parse_observations

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 6, 12, 10, tzinfo=UTC)


@pytest.fixture
def document():
    return json.loads((ROOT / "tests/fixtures/cwa_observation_20261006.json").read_text("utf-8"))


def test_live_contract_wgs84_and_units(document):
    rows = parse_observations(document)
    station = next(r for r in rows if r["id"] == "466940")
    assert station["temperature"] == 24.4
    assert station["rain"] == 9
    assert station["humidity"] == 67  # Already a percentage, not a fraction.
    assert station["lat"] == 25.133314  # WGS84, not first (TWD67) coordinate.


@pytest.mark.parametrize("value", ["-99", "-999", "X", "T", None, "nan", "inf"])
def test_missing_measurements_are_not_zero(document, value):
    element = document["records"]["Station"][0]["WeatherElement"]
    element.update(AirTemperature=value, RelativeHumidity=value, WindSpeed=value)
    element["Now"]["Precipitation"] = value
    rows = parse_observations(document)
    row = next(r for r in rows if r["id"] == document["records"]["Station"][0]["StationId"])
    assert all(row[k] is None for k in ["temperature", "rain", "wind", "humidity"])


def test_trace_and_variable_wind(document):
    element = document["records"]["Station"][0]["WeatherElement"]
    element["Now"]["Precipitation"] = "T"
    element["WindDirection"] = "990"
    row = next(r for r in parse_observations(document) if r["id"] == "466940")
    assert row["rain_note"] == "雨跡" and row["direction"] is None
    assert map_rows([row], "rain", "mm", 0, 100)[0]["label"] == "雨跡"


def test_missing_coordinates_preserve_station(document):
    document["records"]["Station"][0]["GeoInfo"]["Coordinates"] = []
    rows = parse_observations(document)
    assert len(rows) == 2
    assert len(map_rows(rows, "temperature", "°C", -5, 40)) == 1


def test_freshness_excludes_old_and_future(document):
    row = parse_observations(document)[0]
    row["time"] = NOW.isoformat()
    assert fresh_rows([row], NOW)
    assert not fresh_rows([row], NOW + timedelta(hours=2))
    assert not fresh_rows([row], NOW - timedelta(minutes=6))


def test_transaction_failure_and_persisted_throttle(document, tmp_path, monkeypatch):
    store = ObservationStore(tmp_path / "obs.sqlite3")
    calls = []

    def fetch(key, dataset):
        calls.append(dataset)
        return document

    monkeypatch.setattr(observations, "fetch_dataset", fetch)
    assert store.update("private", now=NOW)
    saved = store.read()
    other = ObservationStore(store.path)
    assert not other.update("private", automatic=True, now=NOW + timedelta(minutes=9))
    assert len(calls) == 1
    document["records"]["Station"].append(copy.deepcopy(document["records"]["Station"][0]))
    with pytest.raises(CwaError, match="observation_contract_invalid"):
        other.update("private", now=NOW + timedelta(minutes=10))
    assert other.read()["rows"] == saved["rows"]
    assert other.read()["failed"]
    assert not other.update("private", automatic=True, now=NOW + timedelta(minutes=11))


def test_boundaries_and_raster_style():
    assert len(boundaries()["features"]) == 22
    assert "raster" in map_style(True, "深色")
    assert "raster-brightness-max" in map_style(True, "深色")
    assert "openstreetmap.org" in map_style(True, "街道")
    assert "openstreetmap.org" not in map_style(False)
    assert json.loads(border_layer().to_json())["lineWidthUnits"] == "pixels"
    assert json.loads(label_layer([]).to_json())["characterSet"] == "auto"


def test_representative_labels_use_real_valid_station(document):
    rows = parse_observations(document)
    rows[1]["county"] = rows[0]["county"]
    rows[0]["temperature"] = None
    assert representative_labels(rows, "temperature") == [rows[1]]


def test_stale_response_cannot_replace_good_snapshot(document, tmp_path, monkeypatch):
    monkeypatch.setattr(observations, "fetch_dataset", lambda *args: document)
    store = ObservationStore(tmp_path / "obs.sqlite3")
    store.update("test", now=NOW)
    saved = store.read()["rows"]
    for station in document["records"]["Station"]:
        station["ObsTime"]["DateTime"] = (NOW - timedelta(hours=2)).isoformat()
    with pytest.raises(CwaError, match="no_fresh_observations"):
        store.update("test", now=NOW + timedelta(minutes=10))
    assert store.read()["rows"] == saved


def test_observation_ui_layers_and_forecast_isolation(tmp_path, monkeypatch, document):
    monkeypatch.setenv("WEATHER_DB", str(tmp_path / "weather.sqlite3"))
    monkeypatch.setenv("WEATHER_AUTO_REFRESH", "false")
    monkeypatch.setattr(ui, "api_key", lambda: "")
    monkeypatch.setattr(observations, "fetch_dataset", lambda *args: document)
    # Use current timestamps for UI freshness checks; original fixture remains unchanged.
    for s in document["records"]["Station"]:
        s["ObsTime"]["DateTime"] = datetime.now(UTC).isoformat()
    ObservationStore(tmp_path / "weather_observations.sqlite3").update("test")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.button_group(key="section").set_value("即時觀測").run()
    assert not app.exception
    assert len(app.metric) == 4
    for layer in ["當日累積雨量", "風速風向", "濕度", "氣溫"]:
        app.radio(key="obs_layer").set_value(layer).run()
        assert not app.exception
        assert len(app.dataframe[-1].value) == 2
    app.button_group(key="section").set_value("未來預報").run()
    assert not app.exception
    assert not app.metric  # Observation snapshot cannot appear as a forecast.
