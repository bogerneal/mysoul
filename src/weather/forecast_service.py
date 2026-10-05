"""Serialize fetch/validation/storage; a failed live update never falls back to demo."""

from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from weather.cwa_client import fetch_weekly
from weather.live_parser import parse_live_forecast
from weather.parser import DATASET_ID, ContractError, parse_demo_forecast
from weather.repository import ForecastRepository
from weather.update_log import update_event

_update_lock = Lock()
_last_attempt: dict[str, float] = {}


def refresh_if_due(repository: ForecastRepository, api_key: str, *, now=None) -> int | None:
    """Visitor-triggered refresh, including recovery after an ephemeral disk reset."""
    now = now or datetime.now(UTC)
    state = repository.read(DATASET_ID, "live", now=now)
    if state.last_checked_at and (
        now - datetime.fromisoformat(state.last_checked_at) < timedelta(minutes=30)
    ):
        return None
    try:
        return update_live(repository, api_key, cooldown_seconds=1800)
    except ContractError as exc:
        if exc.code == "update_cooldown":
            return None
        raise


def update_demo(repository: ForecastRepository, document: object, *, now=None) -> int:
    with _update_lock:
        now = now or datetime.now(UTC)
        with update_event(repository, "demo", "update", lambda: now) as event:
            snapshot = parse_demo_forecast(document, fetched_at=now)
            batch_id = repository.save(snapshot)
            event.update(batch_id=batch_id, row_count=len(snapshot.periods))
            return batch_id


def import_live(repository: ForecastRepository, document: object, *, fetched_at: datetime) -> int:
    """Import a saved response retaining its original capture time, even if expired."""
    with _update_lock:
        with update_event(repository, "live", "import", lambda: datetime.now(UTC)) as event:
            if fetched_at.utcoffset() is None or fetched_at > datetime.now(UTC):
                raise ContractError("invalid_capture_time")
            snapshot = parse_live_forecast(document, fetched_at=fetched_at)
            batch_id = repository.save(snapshot)
            event.update(batch_id=batch_id, row_count=len(snapshot.periods))
            return batch_id


def update_live(
    repository: ForecastRepository,
    api_key: str,
    *,
    cooldown_seconds: float = 0,
) -> int:
    with _update_lock:
        with update_event(repository, "live", "update", lambda: datetime.now(UTC)) as event:
            database = str(repository.path.resolve())
            attempt = monotonic()
            if (
                cooldown_seconds
                and attempt - _last_attempt.get(database, -float("inf")) < cooldown_seconds
            ):
                raise ContractError("update_cooldown")
            _last_attempt[database] = attempt
            document = fetch_weekly(api_key)
            now = datetime.now(UTC)
            snapshot = parse_live_forecast(document, fetched_at=now)
            if max(p.end_at for p in snapshot.periods) <= now:
                raise ContractError("expired_live_response")
            if min(p.start_at for p in snapshot.periods) > now + timedelta(hours=12):
                raise ContractError("unexpected_future_forecast")
            batch_id = repository.save(snapshot)
            event.update(batch_id=batch_id, row_count=len(snapshot.periods))
            return batch_id
