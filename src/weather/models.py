"""Immutable normalized output models; timestamps are UTC-aware."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class ForecastPeriod:
    location_code: str
    location_name: str
    start_at: datetime
    end_at: datetime
    min_temp_c: float | None
    max_temp_c: float | None
    quality_flags: tuple[str, ...]


@dataclass(frozen=True)
class ForecastSnapshot:
    dataset_id: str
    mode: Literal["demo", "live"]
    source_issued_at: datetime | None
    fetched_at: datetime
    periods: tuple[ForecastPeriod, ...]
