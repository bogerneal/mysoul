"""Serialize fetch/validation/storage; a failed live update never falls back to demo."""

from datetime import UTC, datetime, timedelta
from threading import Lock

from weather.cwa_client import fetch_weekly
from weather.live_parser import parse_live_forecast
from weather.parser import DATASET_ID, ContractError, parse_demo_forecast
from weather.repository import ForecastRepository

_update_lock = Lock()


def update_demo(repository: ForecastRepository, document: object, *, now=None) -> int:
    with _update_lock:
        now = now or datetime.now(UTC)
        try:
            return repository.save(parse_demo_forecast(document, fetched_at=now))
        except Exception:
            repository.record_failure(DATASET_ID, "demo", now)
            raise


def import_live(repository: ForecastRepository, document: object, *, fetched_at: datetime) -> int:
    """Import a saved response retaining its original capture time, even if expired."""
    with _update_lock:
        try:
            if fetched_at.utcoffset() is None or fetched_at > datetime.now(UTC):
                raise ContractError("invalid_capture_time")
            return repository.save(parse_live_forecast(document, fetched_at=fetched_at))
        except Exception:
            repository.record_failure(DATASET_ID, "live", datetime.now(UTC))
            raise


def update_live(repository: ForecastRepository, api_key: str) -> int:
    with _update_lock:
        try:
            document = fetch_weekly(api_key)
            now = datetime.now(UTC)
            snapshot = parse_live_forecast(document, fetched_at=now)
            if max(p.end_at for p in snapshot.periods) <= now:
                raise ContractError("expired_live_response")
            if min(p.start_at for p in snapshot.periods) > now + timedelta(hours=12):
                raise ContractError("unexpected_future_forecast")
            return repository.save(snapshot)
        except Exception:
            repository.record_failure(DATASET_ID, "live", datetime.now(UTC))
            raise
