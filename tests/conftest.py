from datetime import datetime, timezone
from pathlib import Path

import pytest

from freenews.config import Settings
from freenews.core import NewsHub
from freenews.parse import parse_feed
from freenews.sources import Source
from freenews.trends import parse_google_trends, parse_wikipedia_mostread

FIX = Path(__file__).parent / "fixtures"

SOURCES = [
    Source("bbc-world", "BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "world", "gb", weight=1.3),
    Source("guardian-world", "The Guardian", "https://www.theguardian.com/world/rss", "world", "gb", weight=1.2),
    Source("theverge", "The Verge", "https://www.theverge.com/rss/index.xml", "technology", "us"),
    Source("gnews-us-top", "Google News US", "https://news.google.com/rss?hl=en-US", "top", "us", kind="google_news"),
]
FILES = {"bbc-world": "bbc.xml", "guardian-world": "guardian.xml", "theverge": "verge.atom", "gnews-us-top": "gnews.xml"}


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


@pytest.fixture
def settings():
    # a huge window so fixture dates never age out of the tests
    return Settings(retention_hours=1e6, trending_window_hours=1e6, half_life_hours=8, background_refresh=False)


@pytest.fixture
def hub(settings):
    h = NewsHub(settings, sources=SOURCES)
    for s in SOURCES:
        for a in parse_feed(fixture(FILES[s.id]), s, now=datetime(2030, 1, 1, tzinfo=timezone.utc)):
            h.articles[a.id] = a
        h.status[s.id].ok = True
    h.trends["US"] = parse_google_trends(fixture("trends.xml"))
    h.wikipedia = parse_wikipedia_mostread(fixture("wikipedia_featured.json"))
    h.last_refresh = "2026-10-17T12:00:00Z"
    return h
