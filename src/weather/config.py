"""Read configuration without exposing credentials in representations or errors."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


class ConfigurationError(ValueError):
    """Invalid application configuration."""


@dataclass(frozen=True)
class Settings:
    mode: Literal["demo", "live"] = "demo"
    cwa_api_key: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        mode = values.get("WEATHER_MODE", "demo").strip()
        if mode not in {"demo", "live"}:
            raise ConfigurationError("WEATHER_MODE must be demo or live")
        key = values.get("CWA_API_KEY", "").strip()
        if mode == "live" and not key:
            raise ConfigurationError("CWA_API_KEY is required for live mode")
        return cls(mode=mode, cwa_api_key=key)
