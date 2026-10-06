"""Structured update events containing only allowlisted operational fields."""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from time import monotonic

from weather.cwa_client import CwaError
from weather.parser import DATASET_ID, ContractError
from weather.repository import RepositoryError

logger = logging.getLogger("weather.updates")
SAFE_CODES = frozenset(
    "api_key_required authorization_failed rate_limited retry_after_too_long timeout "
    "connection_failed tls_verification_failed request_failed invalid_json unexpected_response "
    "api_rejected http_error invalid_capture_time expired_live_response unexpected_future_forecast "
    "update_cooldown older_fetch_rejected older_source_rejected older_forecast_rejected "
    "incomplete_county_coverage incomplete_period_coverage invalid_period_coverage "
    "inconsistent_county_coverage unverified_missing_temperature unexpected_dataset "
    "live_response_required unknown_location location_name_mismatch duplicate_location "
    "duplicate_element missing_temperature_element unaligned_periods minimum_exceeds_maximum "
    "invalid_temperature temperature_out_of_range unsupported_schema synthetic_demo_required "
    "missing_field expected_object expected_nonempty_array invalid_timestamp timezone_required "
    "fetched_at_timezone_required duplicate_period overlapping_periods invalid_period "
    "ambiguous_element_value unsupported_element unsupported_unit no_valid_temperatures "
    "invalid_element_name unsupported_database_version invalid_snapshot invalid_location".split()
)


def configure_update_logging():
    """Use stderr so CLI JSON stdout remains machine-readable; never log payloads."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def safe_error_code(exc):
    if isinstance(exc, (CwaError, ContractError, RepositoryError)):
        code = str(exc)
        return code if code in SAFE_CODES else "update_failed"
    if isinstance(exc, (OSError, sqlite3.Error)):
        return "storage_failed"
    return "update_failed"


@contextmanager
def update_event(repository, mode, operation, now):
    started = monotonic()
    event = dict(
        event="forecast_update",
        dataset_id=DATASET_ID,
        mode=mode,
        operation=operation,
        batch_id=None,
        row_count=0,
        result="success",
        error_code=None,
    )
    try:
        yield event
    except (KeyboardInterrupt, SystemExit):
        event.update(result="cancelled", error_code="cancelled")
        raise
    except Exception as exc:
        code = safe_error_code(exc)
        event.update(result="skipped" if code == "update_cooldown" else "failed", error_code=code)
        if code != "update_cooldown":
            try:
                repository.record_failure(DATASET_ID, mode, now())
            except Exception:
                # Preserve the original exception even if failure-state storage is unavailable.
                event["state_error_code"] = "storage_failed"
        raise
    finally:
        event["elapsed_ms"] = round((monotonic() - started) * 1000, 3)
        event["completed_at"] = datetime.now(UTC).isoformat()
        logger.info(json.dumps(event, ensure_ascii=True, separators=(",", ":")))
