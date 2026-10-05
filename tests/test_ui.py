import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from weather import forecast_service, ui
from weather.demo import load_demo_document
from weather.forecast_service import update_demo, update_live
from weather.live_parser import parse_live_forecast
from weather.parser import DATASET_ID, ContractError
from weather.repository import ForecastRepository

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv("WEATHER_DB", str(tmp_path / "weather.sqlite3"))
    monkeypatch.setattr(ui, "api_key", lambda: "")
    monkeypatch.setattr(ui, "current_time", lambda: datetime(2026, 10, 5, tzinfo=UTC))
    return AppTest.from_file(str(APP), default_timeout=20)


def test_empty_live_and_explicit_demo_flow(dashboard):
    app = dashboard.run()
    assert not app.exception
    assert app.button[0].disabled
    assert not app.selectbox
    app.radio[0].set_value("Demo 示範").run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert len(app.selectbox) == 2
    assert app.selectbox(key="day").value == date(2026, 12, 31)
    app.selectbox(key="city").set_value("DEMO-TPE").run()
    app.selectbox(key="day").set_value(date(2027, 1, 1)).run()
    assert not app.exception
    assert "臺北市" in app.subheader[0].value
    app.radio[0].set_value("真實天氣").run()
    assert not app.exception
    assert not app.selectbox  # No implicit demo fallback.


def test_update_failure_keeps_demo_data(dashboard, monkeypatch, tmp_path):
    update_demo(ForecastRepository(tmp_path / "weather.sqlite3"), load_demo_document())
    app = dashboard.run()
    app.radio[0].set_value("Demo 示範").run()

    def fail(*args):
        raise RuntimeError("private internal detail")

    monkeypatch.setattr(ui, "update_demo", fail)
    app.button[0].click().run()
    assert not app.exception
    assert len(app.error) == 1
    assert "private" not in app.error[0].value
    assert len(app.metric) == 3


def test_live_cooldown_blocks_repeated_network_attempt(tmp_path, monkeypatch):
    calls = []

    def fail(key):
        calls.append(key)
        raise RuntimeError("network")

    monkeypatch.setattr(forecast_service, "fetch_weekly", fail)
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    with pytest.raises(RuntimeError):
        update_live(repo, "test", cooldown_seconds=60)
    with pytest.raises(ContractError, match="update_cooldown"):
        update_live(repo, "test", cooldown_seconds=60)
    assert len(calls) == 1


def test_live_stale_filters_and_failed_refresh(dashboard, monkeypatch, tmp_path):
    doc = json.loads(
        (APP.parent / "tests/fixtures/cwa_weekly_20261004_evening.json").read_text(encoding="utf-8")
    )
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    repo.save(parse_live_forecast(doc, fetched_at=datetime(2026, 10, 4, 12, tzinfo=UTC)))
    monkeypatch.setattr(ui, "api_key", lambda: "test")

    def fail(*args, **kwargs):
        raise RuntimeError("private")

    monkeypatch.setattr(ui, "update_live", fail)
    app = dashboard.run()
    assert not app.exception
    assert any("6 小時" in w.value for w in app.warning)
    assert len(app.selectbox(key="city").options) == 22
    assert len(app.selectbox(key="day").options) == 7
    app.selectbox(key="city").set_value("63000000").run()
    assert "臺北市" in app.subheader[0].value
    app.button[0].click().run()
    assert not app.exception
    assert len(app.error) == 1
    assert len(app.metric) == 3
    assert repo.read(DATASET_ID, "live").snapshot is not None


def test_expired_live_has_no_fake_future_dates(dashboard, monkeypatch, tmp_path):
    doc = json.loads(
        (APP.parent / "tests/fixtures/cwa_weekly_20261004_evening.json").read_text(encoding="utf-8")
    )
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    repo.save(parse_live_forecast(doc, fetched_at=datetime(2026, 10, 4, tzinfo=UTC)))
    monkeypatch.setattr(ui, "current_time", lambda: datetime(2026, 11, 1, tzinfo=UTC))
    app = dashboard.run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert not app.metric
    assert any("沒有今天起" in w.value for w in app.warning)
