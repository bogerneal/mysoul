"""Run an explicitly labelled, offline contract demonstration."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from weather.config import ConfigurationError, Settings
from weather.demo import load_demo_document
from weather.parser import ContractError, parse_demo_forecast


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic weather data demo (no live API)")
    parser.add_argument("--fixture", type=Path, help="Optional synthetic v1 JSON file")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        if settings.mode != "demo":
            raise ConfigurationError(
                "weather-demo requires WEATHER_MODE=demo; "
                "use weather-data update-live for live data"
            )
        document = (
            json.loads(args.fixture.read_text(encoding="utf-8"))
            if args.fixture is not None
            else load_demo_document()
        )
        snapshot = parse_demo_forecast(document, fetched_at=datetime.now(UTC))
    except (ConfigurationError, ContractError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError):
        print("Error: cannot_read_fixture_json", file=sys.stderr)
        return 2
    output = {
        "notice": "DEMO / SYNTHETIC DATA - NOT A LIVE FORECAST",
        "period_count": len(snapshot.periods),
        "snapshot": asdict(snapshot),
    }
    print(json.dumps(output, ensure_ascii=True, indent=2, default=lambda value: value.isoformat()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
