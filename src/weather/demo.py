"""Packaged synthetic data; no network access."""

import json
from importlib.resources import files


def load_demo_document() -> dict:
    return json.loads(
        files("weather").joinpath("fixtures/synthetic_weekly_v1.json").read_text("utf-8")
    )
