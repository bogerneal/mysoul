"""Validated CWA observations; independent snapshots and persisted request throttling."""

import json
import logging
import math
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from weather.cwa_client import CwaError, fetch_dataset

DATASET = "O-A0003-001"
_LOCK = threading.Lock()
MISSING = {"", "X", "T", "-99", "-99.0", "-999", "-999.0", "-98", "-98.0"}


def number(value, low, high):
    if value is None or str(value).strip() in MISSING or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def parse_observations(document):
    """Keep absent measurements explicit; reject broken station identity/time contracts."""
    try:
        stations = document["records"]["Station"]
        if not isinstance(stations, list) or not stations:
            raise ValueError
        rows, ids = [], set()
        for station in stations:
            identity = station["StationId"]
            name = station["StationName"]
            if not isinstance(identity, str) or not identity or identity in ids:
                raise ValueError
            if not isinstance(name, str) or not name:
                raise ValueError
            ids.add(identity)
            observed = datetime.fromisoformat(station["ObsTime"]["DateTime"])
            if observed.tzinfo is None:
                raise ValueError
            geo, weather = station["GeoInfo"], station["WeatherElement"]
            coordinates = next(
                (p for p in geo["Coordinates"] if p["CoordinateName"] == "WGS84"), {}
            )
            rain_raw = str(weather.get("Now", {}).get("Precipitation", ""))
            rows.append(
                {
                    "id": identity,
                    "name": name,
                    "county": str(geo.get("CountyName", "未知縣市")),
                    "town": str(geo.get("TownName", "")),
                    "time": observed.astimezone(UTC).isoformat(),
                    "lat": number(coordinates.get("StationLatitude"), -90, 90),
                    "lon": number(coordinates.get("StationLongitude"), -180, 180),
                    "altitude": number(geo.get("StationAltitude"), -500, 10000),
                    "temperature": number(weather.get("AirTemperature"), -80, 65),
                    "rain": number(rain_raw, 0, 3000),
                    "rain_note": "雨跡"
                    if rain_raw == "T"
                    else "連續 6 小時無降水"
                    if rain_raw in {"-98", "-98.0"}
                    else "",
                    "wind": number(weather.get("WindSpeed"), 0, 150),
                    "direction": number(weather.get("WindDirection"), 0, 360),
                    "humidity": number(weather.get("RelativeHumidity"), 0, 100),
                    "weather": str(weather.get("Weather", "")),
                }
            )
        return sorted(rows, key=lambda r: r["id"])
    except (KeyError, TypeError, ValueError, StopIteration):
        raise CwaError("observation_contract_invalid") from None


def fresh_rows(rows, now):
    return [
        r
        for r in rows
        if -timedelta(minutes=5) <= now - datetime.fromisoformat(r["time"]) <= timedelta(hours=1)
    ]


class ObservationStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS observation_snapshot "
                "(id INTEGER PRIMARY KEY CHECK(id=1), fetched TEXT, payload TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS observation_attempt "
                "(id INTEGER PRIMARY KEY CHECK(id=1), attempted TEXT, failed INTEGER)"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self.connect() as db:
            snapshot = db.execute("SELECT fetched,payload FROM observation_snapshot").fetchone()
            attempt = db.execute("SELECT attempted,failed FROM observation_attempt").fetchone()
        return {
            "fetched": datetime.fromisoformat(snapshot[0]) if snapshot else None,
            "rows": json.loads(snapshot[1]) if snapshot else [],
            "attempted": datetime.fromisoformat(attempt[0]) if attempt else None,
            "failed": bool(attempt and attempt[1]),
        }

    def update(self, key, *, automatic=False, now=None):
        now = now or datetime.now(UTC)
        started = perf_counter()
        with _LOCK:
            # Reserve an attempt transactionally, including across server processes.
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                attempt = db.execute("SELECT attempted FROM observation_attempt").fetchone()
                seconds = 600 if automatic else 60
                if attempt and (now - datetime.fromisoformat(attempt[0])).total_seconds() < seconds:
                    return False
                db.execute(
                    "INSERT OR REPLACE INTO observation_attempt VALUES(1,?,1)", (now.isoformat(),)
                )
            count, outcome = 0, "failed"
            try:
                rows = parse_observations(fetch_dataset(key, DATASET))
                valid = fresh_rows(rows, now)
                if not any(
                    any(r[f] is not None for f in ("temperature", "rain", "wind", "humidity"))
                    for r in valid
                ):
                    raise CwaError("no_fresh_observations")
                previous = self.read()["rows"]
                if previous and max(r["time"] for r in rows) < max(r["time"] for r in previous):
                    raise CwaError("older_observations")
                count = len(rows)
                with self.connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO observation_snapshot VALUES(1,?,?)",
                        (now.isoformat(), json.dumps(rows, ensure_ascii=False)),
                    )
                    db.execute("UPDATE observation_attempt SET failed=0 WHERE id=1")
                outcome = "success"
                return True
            finally:
                logging.getLogger("weather.updates").info(
                    json.dumps(
                        {
                            "dataset_id": DATASET,
                            "result": outcome,
                            "rows": count,
                            "duration_ms": round((perf_counter() - started) * 1000),
                        }
                    )
                )
