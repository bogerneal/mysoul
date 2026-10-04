import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from weather.forecast_service import update_demo
from weather.parser import DATASET_ID, ContractError, parse_demo_forecast
from weather.repository import ForecastRepository, RepositoryError

NOW = datetime(2026, 12, 31, 9, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path):
    return ForecastRepository(tmp_path / "weather.sqlite3")


def snapshot(document, **changes):
    return replace(parse_demo_forecast(document, fetched_at=NOW), **changes)


def test_repeat_import_and_restart_preserve_batch(repo, document):
    first = update_demo(repo, document, now=NOW)
    assert update_demo(repo, document, now=NOW + timedelta(hours=1)) == first
    restarted = ForecastRepository(repo.path)
    state = restarted.read(DATASET_ID, "demo", now=NOW + timedelta(hours=1))
    assert state.snapshot == snapshot(document)
    assert datetime.fromisoformat(state.last_success_at) == NOW + timedelta(hours=1)
    with repo.connection() as db:
        assert db.execute("SELECT count(*) FROM forecast_batches").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM forecast_periods").fetchone()[0] == 4
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_revision_retains_two_snapshots_and_reuses_retained_hash(repo, document):
    initial = snapshot(document)
    first = repo.save(initial)
    changed = replace(
        initial, periods=(replace(initial.periods[0], max_temp_c=26), *initial.periods[1:])
    )
    second = repo.save(changed)
    assert second != first
    assert repo.save(initial) == first
    third = replace(
        initial, periods=(replace(initial.periods[0], max_temp_c=27), *initial.periods[1:])
    )
    third_id = repo.save(third)
    repo.save(third)
    with repo.connection() as db:
        assert {row[0] for row in db.execute("SELECT id FROM forecast_batches")} == {
            first,
            third_id,
        }


def test_demo_live_are_isolated(repo, document):
    demo = snapshot(document)
    first = repo.save(demo)
    assert repo.read(DATASET_ID, "live").snapshot is None
    second = repo.save(replace(demo, mode="live"))
    assert first != second
    repo.record_failure(DATASET_ID, "live", NOW)
    assert repo.read(DATASET_ID, "demo").last_error_code is None
    assert repo.read(DATASET_ID, "live").last_error_code == "update_failed"


def test_parser_failure_preserves_last_success(repo, document):
    first = update_demo(repo, document, now=NOW)
    document["schema_version"] = "bad-secret-input"
    with pytest.raises(ContractError):
        update_demo(repo, document, now=NOW + timedelta(minutes=1))
    state = repo.read(DATASET_ID, "demo", now=NOW)
    assert state.batch_id == first
    assert state.last_error_code == "update_failed"
    assert datetime.fromisoformat(state.last_success_at) == NOW


def test_partial_sql_failure_rolls_back_everything(repo, document):
    first = update_demo(repo, document, now=NOW)
    with repo.connection() as db:
        db.execute("""CREATE TRIGGER fail_midway BEFORE INSERT ON forecast_periods
                      WHEN NEW.location_code='DEMO-TPE'
                      BEGIN SELECT RAISE(ABORT,'simulated failure'); END""")
    document["source_issued_at"] = "2026-12-31T08:00:00Z"
    with pytest.raises(sqlite3.IntegrityError):
        update_demo(repo, document, now=NOW + timedelta(minutes=1))
    assert repo.read(DATASET_ID, "demo").batch_id == first
    with repo.connection() as db:
        assert db.execute("SELECT count(*) FROM forecast_batches").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM forecast_periods").fetchone()[0] == 4


def test_no_time_regression(repo, document):
    current = snapshot(document, source_issued_at=NOW)
    repo.save(current)
    with pytest.raises(RepositoryError, match="older_source_rejected"):
        repo.save(replace(current, source_issued_at=NOW - timedelta(hours=1)))
    with pytest.raises(RepositoryError, match="older_source_rejected"):
        repo.save(replace(current, source_issued_at=None))
    with pytest.raises(RepositoryError, match="older_fetch_rejected"):
        repo.save(replace(current, fetched_at=NOW - timedelta(minutes=1)))


def test_staleness_and_empty_state(repo, document):
    assert repo.read(DATASET_ID, "demo", now=NOW).stale
    repo.save(snapshot(document))
    assert not repo.read(DATASET_ID, "demo", now=NOW).stale
    assert repo.read(DATASET_ID, "demo", now=NOW + timedelta(hours=7)).stale
    later = datetime(2027, 1, 2, tzinfo=UTC)
    repo.save(snapshot(document, fetched_at=later))
    assert repo.read(DATASET_ID, "demo", now=later).stale


def test_order_does_not_change_content_hash(repo, document):
    data = snapshot(document)
    assert repo.save(data) == repo.save(replace(data, periods=tuple(reversed(data.periods))))


def test_invalid_snapshot_does_not_change_current(repo, document):
    data = snapshot(document)
    first = repo.save(data)
    with pytest.raises(RepositoryError):
        repo.save(replace(data, periods=()))
    with pytest.raises(RepositoryError):
        repo.save(replace(data, periods=data.periods + data.periods))
    assert repo.read(DATASET_ID, "demo").batch_id == first


def test_future_database_version_rejected(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(RepositoryError, match="unsupported_database_version"):
        ForecastRepository(path)
