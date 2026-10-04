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
from weather.forecast_service import update_demo
from weather.parser import DATASET_ID, ContractError
from weather.repository import ForecastRepository, RepositoryError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Weather storage and CWA contract capture")
    commands = parser.add_subparsers(dest="command", required=True)
    update = commands.add_parser("update-demo", help="Import explicitly synthetic data into SQLite")
    update.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    update.add_argument("--fixture", type=Path)
    status = commands.add_parser("status", help="Read a fixed snapshot without network access")
    status.add_argument("--db", type=Path, default=Path("data/weather.sqlite3"))
    status.add_argument("--mode", choices=["demo", "live"], required=True)
    capture = commands.add_parser("capture-cwa", help="Capture unverified JSON, never publish it")
    capture.add_argument("--prompt-key", action="store_true", help="Read Key with hidden input")
    args = parser.parse_args(argv)
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
        if args.command == "update-demo":
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
            result = asdict(repository.read(DATASET_ID, args.mode))
            result["mode"] = args.mode
            result["notice"] = "SYNTHETIC DATA" if args.mode == "demo" else "LIVE DATA"
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
