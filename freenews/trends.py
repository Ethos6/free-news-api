"""What people are searching for and reading right now.

* Google Trends "Trending now" RSS (per country)
* Wikipedia most-read articles (official Wikimedia feed API)
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .models import TrendItem


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1]


def _child_text(el: ET.Element, name: str) -> str:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


SKIP_WIKI = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:")


def google_trends_url(geo: str) -> str:
    return f"https://trends.google.com/trending/rss?geo={geo.upper()}"


def parse_google_trends(text: str | bytes) -> list[TrendItem]:
    try:
        root = ET.fromstring(text if isinstance(text, bytes) else text.encode("utf-8"))
    except ET.ParseError:
        return []
    out: list[TrendItem] = []
    for item in root.iter("item"):
        title = _child_text(item, "title")
        if not title:
            continue
        news = [
            {
                "title": _child_text(n, "news_item_title"),
                "url": _child_text(n, "news_item_url"),
                "source": _child_text(n, "news_item_source"),
            }
            for n in item
            if _local(n.tag) == "news_item"
        ]
        out.append(
            TrendItem(
                title=title,
                source="google_trends",
                traffic=_child_text(item, "approx_traffic") or None,
                image=_child_text(item, "picture") or None,
                url=news[0]["url"] if news else None,
                news=[n for n in news if n["url"]],
            )
        )
    return out


def wikipedia_mostread_url(lang: str = "en", day: datetime | None = None) -> str:
    day = day or (datetime.now(timezone.utc) - timedelta(days=1))
    return f"https://{lang}.wikipedia.org/api/rest_v1/feed/featured/{day:%Y/%m/%d}"


def parse_wikipedia_mostread(text: str | bytes, limit: int = 25) -> list[TrendItem]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    arts = (data.get("mostread") or {}).get("articles") or []
    out = []
    for a in arts:
        title = a.get("title", "")
        if title.startswith(SKIP_WIKI):
            continue
        out.append(
            TrendItem(
                title=a.get("normalizedtitle") or title.replace("_", " "),
                source="wikipedia",
                traffic=f"{a.get('views', 0):,} views",
                url=((a.get("content_urls") or {}).get("desktop") or {}).get("page"),
                description=(a.get("extract") or "")[:400] or None,
                image=(a.get("thumbnail") or {}).get("source"),
            )
        )
        if len(out) >= limit:
            break
    return out
