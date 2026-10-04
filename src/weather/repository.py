"""Transactional, mode-isolated SQLite snapshots. No API credentials are stored."""

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from weather.models import ForecastPeriod, ForecastSnapshot


class RepositoryError(ValueError):
    """Safe public error code."""


def stamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise RepositoryError("timezone_required")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def canonical(snapshot: ForecastSnapshot) -> str:
    if snapshot.mode not in {"demo", "live"} or not snapshot.periods:
        raise RepositoryError("invalid_snapshot")
    stamp(snapshot.fetched_at)
    seen = set()
    names = {}
    ends = {}
    rows = []
    for period in sorted(snapshot.periods, key=lambda p: (p.location_code, p.start_at, p.end_at)):
        start, end = stamp(period.start_at), stamp(period.end_at)
        key = (period.location_code, start, end)
        if end <= start or key in seen or start < ends.get(period.location_code, start):
            raise RepositoryError("invalid_period")
        if not period.location_code or not period.location_name:
            raise RepositoryError("invalid_location")
        if names.setdefault(period.location_code, period.location_name) != period.location_name:
            raise RepositoryError("location_name_mismatch")
        ends[period.location_code] = end
        seen.add(key)
        low, high = period.min_temp_c, period.max_temp_c
        for value in (low, high):
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(value) or not -80 <= value <= 65
            ):
                raise RepositoryError("invalid_temperature")
        if low is not None and high is not None and low > high:
            raise RepositoryError("minimum_exceeds_maximum")
        row = asdict(period)
        row.update(start_at=start, end_at=end)
        rows.append(row)
    if all(p.min_temp_c is None and p.max_temp_c is None for p in snapshot.periods):
        raise RepositoryError("no_valid_temperatures")
    return json.dumps(
        {
            "dataset_id": snapshot.dataset_id,
            "mode": snapshot.mode,
            "source_issued_at": stamp(snapshot.source_issued_at)
            if snapshot.source_issued_at
            else None,
            "periods": rows,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class StoredForecast:
    batch_id: int | None
    snapshot: ForecastSnapshot | None
    last_checked_at: str | None
    last_success_at: str | None
    last_error_code: str | None
    stale: bool


class ForecastRepository:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RepositoryError("unsupported_database_version")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS forecast_batches (
                    id INTEGER PRIMARY KEY, dataset_id TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK(mode IN ('demo','live')),
                    content_sha256 TEXT NOT NULL, source_issued_at TEXT,
                    fetched_at TEXT NOT NULL,
                    UNIQUE(dataset_id, mode, content_sha256),
                    UNIQUE(id, dataset_id, mode)
                );
                CREATE TABLE IF NOT EXISTS forecast_periods (
                    batch_id INTEGER NOT NULL REFERENCES forecast_batches(id) ON DELETE CASCADE,
                    location_code TEXT NOT NULL, location_name TEXT NOT NULL,
                    start_at TEXT NOT NULL, end_at TEXT NOT NULL CHECK(end_at > start_at),
                    min_temp_c REAL, max_temp_c REAL, quality_flags TEXT NOT NULL,
                    CHECK(min_temp_c IS NULL OR max_temp_c IS NULL OR min_temp_c <= max_temp_c),
                    PRIMARY KEY(batch_id, location_code, start_at, end_at)
                );
                CREATE TABLE IF NOT EXISTS dataset_state (
                    dataset_id TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('demo','live')),
                    current_batch_id INTEGER, last_checked_at TEXT NOT NULL,
                    last_success_at TEXT, last_error_code TEXT,
                    PRIMARY KEY(dataset_id, mode),
                    FOREIGN KEY(current_batch_id, dataset_id, mode)
                        REFERENCES forecast_batches(id, dataset_id, mode)
                );
                PRAGMA user_version=1;
                COMMIT;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, snapshot: ForecastSnapshot) -> int:
        payload = canonical(snapshot)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        data = json.loads(payload)
        fetched = stamp(snapshot.fetched_at)
        dataset, mode = snapshot.dataset_id, snapshot.mode
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT b.*, s.last_success_at FROM dataset_state s "
                "JOIN forecast_batches b ON b.id=s.current_batch_id "
                "WHERE s.dataset_id=? AND s.mode=?",
                (dataset, mode),
            ).fetchone()
            if current:
                if fetched < current["last_success_at"]:
                    raise RepositoryError("older_fetch_rejected")
                issued = data["source_issued_at"]
                if current["source_issued_at"] and (
                    not issued or issued < current["source_issued_at"]
                ):
                    raise RepositoryError("older_source_rejected")
            existing = db.execute(
                "SELECT id FROM forecast_batches "
                "WHERE dataset_id=? AND mode=? AND content_sha256=?",
                (dataset, mode, digest),
            ).fetchone()
            if existing:
                batch_id = existing["id"]
            else:
                batch_id = db.execute(
                    "INSERT INTO forecast_batches "
                    "(dataset_id,mode,content_sha256,source_issued_at,fetched_at) "
                    "VALUES (?,?,?,?,?)",
                    (dataset, mode, digest, data["source_issued_at"], fetched),
                ).lastrowid
                db.executemany(
                    "INSERT INTO forecast_periods VALUES (?,?,?,?,?,?,?,?)",
                    [
                        (
                            batch_id,
                            p["location_code"],
                            p["location_name"],
                            p["start_at"],
                            p["end_at"],
                            p["min_temp_c"],
                            p["max_temp_c"],
                            json.dumps(p["quality_flags"]),
                        )
                        for p in data["periods"]
                    ],
                )
            db.execute(
                "INSERT INTO dataset_state VALUES (?,?,?,?,?,NULL) "
                "ON CONFLICT(dataset_id,mode) DO UPDATE SET "
                "current_batch_id=excluded.current_batch_id,"
                "last_checked_at=excluded.last_checked_at,last_success_at=excluded.last_success_at,"
                "last_error_code=NULL",
                (dataset, mode, batch_id, fetched, fetched),
            )
            keep = {batch_id}
            if current:
                keep.add(current["id"])
            # On identical refresh, also preserve the previous successful batch.
            if current and current["id"] == batch_id:
                previous = db.execute(
                    "SELECT id FROM forecast_batches WHERE dataset_id=? AND mode=? AND id<>? "
                    "ORDER BY id DESC LIMIT 1",
                    (dataset, mode, batch_id),
                ).fetchone()
                if previous:
                    keep.add(previous["id"])
            for row in db.execute(
                "SELECT id FROM forecast_batches WHERE dataset_id=? AND mode=?",
                (dataset, mode),
            ).fetchall():
                if row["id"] not in keep:
                    db.execute("DELETE FROM forecast_batches WHERE id=?", (row["id"],))
        return batch_id

    def record_failure(self, dataset: str, mode: str, now: datetime) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO dataset_state VALUES (?,?,NULL,?,NULL,'update_failed') "
                "ON CONFLICT(dataset_id,mode) DO UPDATE SET "
                "last_checked_at=excluded.last_checked_at,"
                "last_error_code='update_failed' WHERE excluded.last_checked_at >= last_checked_at",
                (dataset, mode, stamp(now)),
            )

    def read(self, dataset: str, mode: str, *, now: datetime | None = None) -> StoredForecast:
        now = now or datetime.now(UTC)
        stamp(now)
        with self.connection() as db:
            db.execute("BEGIN")
            state = db.execute(
                "SELECT * FROM dataset_state WHERE dataset_id=? AND mode=?",
                (dataset, mode),
            ).fetchone()
            if not state or state["current_batch_id"] is None:
                return StoredForecast(
                    None,
                    None,
                    state["last_checked_at"] if state else None,
                    None,
                    state["last_error_code"] if state else None,
                    True,
                )
            batch = db.execute(
                "SELECT * FROM forecast_batches WHERE id=?",
                (state["current_batch_id"],),
            ).fetchone()
            periods = tuple(
                ForecastPeriod(
                    p["location_code"],
                    p["location_name"],
                    datetime.fromisoformat(p["start_at"]),
                    datetime.fromisoformat(p["end_at"]),
                    p["min_temp_c"],
                    p["max_temp_c"],
                    tuple(json.loads(p["quality_flags"])),
                )
                for p in db.execute(
                    "SELECT * FROM forecast_periods WHERE batch_id=? "
                    "ORDER BY location_code,start_at",
                    (batch["id"],),
                )
            )
            snapshot = ForecastSnapshot(
                dataset,
                mode,
                datetime.fromisoformat(batch["source_issued_at"])
                if batch["source_issued_at"]
                else None,
                datetime.fromisoformat(batch["fetched_at"]),
                periods,
            )
            stale = (
                now - datetime.fromisoformat(state["last_success_at"]) > timedelta(hours=6)
                or max(p.end_at for p in periods) <= now
            )
            return StoredForecast(
                batch["id"],
                snapshot,
                state["last_checked_at"],
                state["last_success_at"],
                state["last_error_code"],
                stale,
            )
