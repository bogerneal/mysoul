"""Offline update coordination. Live publication remains gated on contract verification."""

from datetime import UTC, datetime
from threading import Lock

from weather.parser import DATASET_ID, parse_demo_forecast
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
