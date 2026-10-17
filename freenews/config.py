"""Configuration from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # Google News editions to follow (ISO country codes). More countries = more coverage, more requests.
    countries: list[str] = field(default_factory=lambda: ["us", "gb", "in", "au", "ca"])
    # Google Trends regions for /trends
    trend_geos: list[str] = field(default_factory=lambda: ["US", "GB", "IN"])
    include_publishers: bool = True
    refresh_minutes: float = 15.0
    retention_hours: float = 48.0
    trending_window_hours: float = 24.0
    half_life_hours: float = 8.0
    timeout: float = 15.0
    concurrency: int = 16
    api_keys: list[str] = field(default_factory=list)
    rate_limit: int = 0
    proxies: list[str] = field(default_factory=list)
    snapshot_path: str | None = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    background_refresh: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(os.getenv("FREENEWS_ENV_FILE", ".env"))
        return cls(
            countries=_list("FREENEWS_COUNTRIES", "us,gb,in,au,ca"),
            trend_geos=_list("FREENEWS_TREND_GEOS", "US,GB,IN"),
            include_publishers=os.getenv("FREENEWS_PUBLISHER_FEEDS", "true").lower() not in ("0", "false", "no"),
            refresh_minutes=_num("FREENEWS_REFRESH_MINUTES", 15),
            retention_hours=_num("FREENEWS_RETENTION_HOURS", 48),
            trending_window_hours=_num("FREENEWS_TRENDING_WINDOW_HOURS", 24),
            half_life_hours=_num("FREENEWS_HALF_LIFE_HOURS", 8),
            timeout=_num("FREENEWS_TIMEOUT", 15),
            concurrency=int(_num("FREENEWS_CONCURRENCY", 16)),
            api_keys=_list("FREENEWS_API_KEYS"),
            rate_limit=int(_num("FREENEWS_RATE_LIMIT", 0)),
            proxies=_list("FREENEWS_PROXIES"),
            snapshot_path=os.getenv("FREENEWS_SNAPSHOT") or None,
            cors_origins=_list("FREENEWS_CORS_ORIGINS", "*"),
            background_refresh=os.getenv("FREENEWS_BACKGROUND_REFRESH", "true").lower() not in ("0", "false", "no"),
        )
