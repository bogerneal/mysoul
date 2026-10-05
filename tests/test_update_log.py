import json
import logging
import sqlite3
from datetime import UTC, datetime

import pytest

from weather import forecast_service
from weather.cwa_client import CwaError
from weather.forecast_service import update_demo, update_live
from weather.parser import DATASET_ID, ContractError
from weather.repository import ForecastRepository


def events(caplog):
    return [json.loads(r.message) for r in caplog.records if r.name == "weather.updates"]


def test_success_logs_batch_count_duration_without_document(tmp_path, document, caplog):
    caplog.set_level(logging.INFO, logger="weather.updates")
    repo = ForecastRepository(tmp_path / "db.sqlite3")
    first = update_demo(repo, document)
    assert update_demo(repo, document) == first
    for event in events(caplog):
        assert event["batch_id"] == first
        assert event["row_count"] == 4
        assert event["dataset_id"] == DATASET_ID
        assert event["elapsed_ms"] >= 0
        assert event["result"] == "success"
        assert event["error_code"] is None
    assert len(events(caplog)) == 2
    assert "WeatherElement" not in caplog.text


@pytest.mark.parametrize(
    "exception,expected",
    [
        (CwaError("authorization_failed"), "authorization_failed"),
        (CwaError("https://example.invalid/?Authorization=PRIVATE"), "update_failed"),
        (RuntimeError("PRIVATE"), "update_failed"),
        (sqlite3.OperationalError("PRIVATE"), "storage_failed"),
    ],
)
def test_failure_log_redacts_details(tmp_path, monkeypatch, caplog, exception, expected):
    caplog.set_level(logging.INFO, logger="weather.updates")
    repo = ForecastRepository(tmp_path / "db.sqlite3")

    def fail(key):
        raise exception

    monkeypatch.setattr(forecast_service, "fetch_weekly", fail)
    with pytest.raises(type(exception)):
        update_live(repo, "PRIVATE")
    event = events(caplog)[-1]
    assert event["result"] == "failed"
    assert event["error_code"] == expected
    assert event["batch_id"] is None
    assert "PRIVATE" not in caplog.text
    assert "Authorization" not in caplog.text
    assert repo.read(DATASET_ID, "live").last_error_code == "update_failed"


def test_failed_state_write_does_not_mask_original_failure(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="weather.updates")
    repo = ForecastRepository(tmp_path / "db.sqlite3")

    def storage_failure(*args):
        raise sqlite3.OperationalError("PRIVATE")

    monkeypatch.setattr(repo, "record_failure", storage_failure)
    with pytest.raises(ContractError, match="unsupported_schema"):
        update_demo(repo, {})
    assert events(caplog)[-1]["state_error_code"] == "storage_failed"
    assert "PRIVATE" not in caplog.text


def test_cooldown_logs_skipped_without_marking_successful_data_failed(
    tmp_path, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="weather.updates")
    repo = ForecastRepository(tmp_path / "db.sqlite3")
    monkeypatch.setattr(forecast_service, "_last_attempt", {str(repo.path.resolve()): 100.0})
    monkeypatch.setattr(forecast_service, "monotonic", lambda: 101.0)
    with pytest.raises(ContractError, match="update_cooldown"):
        update_live(repo, "PRIVATE", cooldown_seconds=60)
    assert events(caplog)[-1]["result"] == "skipped"
    assert repo.read(DATASET_ID, "live", now=datetime.now(UTC)).last_error_code is None
