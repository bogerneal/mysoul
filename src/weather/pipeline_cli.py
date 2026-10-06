"""Explicit demo storage and private CWA contract capture commands."""

import argparse
import getpass
import json
import os
import sqlite3
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from weather.cwa_client import CwaError, fetch_weekly
from weather.demo import load_demo_document
from weather.forecast_service import import_live, update_demo, update_live
from weather.parser import DATASET_ID, ContractError, _timestamp
from weather.presentation import summarize
from weather.repository import ForecastRepository, RepositoryError
from weather.update_log import configure_update_logging


def main(argv=None) -> int:
    configure_update_logging()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Weather storage and CWA contract capture")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("update-demo", help="Import explicitly synthetic data into SQLite")
    update.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    update.add_argument("--fixture", type=Path)
    status = commands.add_parser("status", help="Read a fixed snapshot without network access")
    status.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    status.add_argument("--mode", choices=["demo", "live"], required=True)
    status.add_argument("--summary", action="store_true", help="Readable Taiwan-time summary")
    status.add_argument("--location", help="County name or code (requires --summary)")
    live = commands.add_parser("update-live", help="Fetch, validate and store real CWA forecasts")
    live.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    live.add_argument("--prompt-key", action="store_true")
    imported = commands.add_parser("import-cwa", help="Import a captured CWA response, no network")
    imported.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    imported.add_argument("--file", type=Path, required=True)
    imported.add_argument(
        "--fetched-at", required=True, help="Original capture ISO timestamp with timezone"
    )
    capture = commands.add_parser("capture-cwa", help="Capture unverified JSON, never publish it")
    capture.add_argument("--prompt-key", action="store_true", help="Read Key with hidden input")
    args = parser.parse_args(argv)
    if args.command == "status" and args.location and not args.summary:
        parser.error("--location requires --summary")
    try:
        if args.command == "capture-cwa":
            key = (
                getpass.getpass("CWA API Key (hidden): ")
                if args.prompt_key
                else os.getenv("CWA_API_KEY", "")
            )
            document = fetch_weekly(key)
            # Do not persist a server response if it happens to echo the credential.
            serialized = json.dumps(document, ensure_ascii=True, indent=2)
            if key in serialized:
                raise CwaError("response_contains_credential")
            directory = Path("data/private")
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / ("cwa-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
            with path.open("x", encoding="utf-8") as output:
                output.write(serialized)
            print(
                json.dumps(
                    {
                        "status": "captured_unverified",
                        "path": str(path),
                        "notice": "Contract review required; NOT imported into live database.",
                    }
                )
            )
            return 0
        repository = ForecastRepository(args.db)
        if args.command == "update-live":
            key = (
                getpass.getpass("CWA API Key (hidden): ")
                if args.prompt_key
                else os.getenv("CWA_API_KEY", "")
            )
            batch_id = update_live(repository, key)
            print(json.dumps({"mode": "live", "notice": "CWA FORECAST", "batch_id": batch_id}))
        elif args.command == "import-cwa":
            try:
                document = json.loads(args.file.read_text(encoding="utf-8"))
                fetched_at = _timestamp(args.fetched_at)
            except (OSError, UnicodeError, ValueError):
                repository.record_failure(DATASET_ID, "live", datetime.now(UTC))
                raise RepositoryError("invalid_capture_file_or_time") from None
            batch_id = import_live(repository, document, fetched_at=fetched_at)
            print(
                json.dumps(
                    {
                        "mode": "live",
                        "notice": "SAVED CWA RESPONSE; NOT A NEW FETCH",
                        "batch_id": batch_id,
                    }
                )
            )
        elif args.command == "update-demo":
            try:
                document = (
                    json.loads(args.fixture.read_text(encoding="utf-8"))
                    if args.fixture
                    else load_demo_document()
                )
            except (OSError, UnicodeError, ValueError):
                repository.record_failure(DATASET_ID, "demo", datetime.now(UTC))
                raise RepositoryError("cannot_read_fixture_json") from None
            batch_id = update_demo(repository, document)
            print(json.dumps({"mode": "demo", "notice": "SYNTHETIC DATA", "batch_id": batch_id}))
        else:
            state = repository.read(DATASET_ID, args.mode)
            if args.summary:
                print(summarize(state, args.mode, args.location))
                return 0
            result = {
                "mode": args.mode,
                "notice": "SYNTHETIC DATA" if args.mode == "demo" else "LIVE DATA",
                "query_does_not_fetch": True,
                **asdict(state),
            }
            print(
                json.dumps(
                    result, ensure_ascii=True, indent=2, default=lambda value: value.isoformat()
                )
            )
    except (CwaError, ContractError, RepositoryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error):
        print("Error: storage_failed", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("Error: cancelled", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
