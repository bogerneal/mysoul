from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from weather import forecast_service
from weather.forecast_service import refresh_if_due
from weather.parser import DATASET_ID
from weather.repository import ForecastRepository

NOW = datetime(2026, 10, 6, tzinfo=UTC)


def test_empty_database_triggers_rebuild(tmp_path, monkeypatch):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")
    update = Mock(return_value=1)
    monkeypatch.setattr(forecast_service, "update_live", update)
    assert refresh_if_due(repo, "test", now=NOW) == 1
    update.assert_called_once_with(repo, "test", cooldown_seconds=1800)


def test_failed_attempt_survives_restart_and_throttles_retries(tmp_path, monkeypatch):
    path = tmp_path / "weather.sqlite3"
    repo = ForecastRepository(path)
    repo.record_failure(DATASET_ID, "live", NOW)
    update = Mock(return_value=2)
    monkeypatch.setattr(forecast_service, "update_live", update)
    restarted = ForecastRepository(path)
    assert refresh_if_due(restarted, "test", now=NOW + timedelta(minutes=29)) is None
    update.assert_not_called()
    assert refresh_if_due(restarted, "test", now=NOW + timedelta(minutes=30)) == 2


def test_auto_refresh_failure_never_creates_demo(tmp_path, monkeypatch):
    repo = ForecastRepository(tmp_path / "weather.sqlite3")

    def fail(key):
        raise RuntimeError("offline")

    monkeypatch.setattr(forecast_service, "fetch_weekly", fail)
    with pytest.raises(RuntimeError):
        refresh_if_due(repo, "test")
    assert repo.read(DATASET_ID, "demo").snapshot is None
    assert repo.read(DATASET_ID, "live").last_error_code == "update_failed"
