"""Build a static, serverless copy of the API (plain JSON + RSS files).

    freenews build --out site

GitHub Actions runs this on a schedule and publishes the folder to GitHub Pages, so
anyone can fork the repo and get a free hosted news API with no server at all:

    https://<user>.github.io/free-news-api/v1/trending.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .api import stories_rss
from .core import NewsHub
from .sources import CATEGORIES

STATIC = Path(__file__).with_name("static")


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _stories(hub: NewsHub, **kw: Any) -> list[dict]:
    return [s.model_copy(update={"articles": s.articles[:5]}).model_dump() for s in hub.trending(**kw)]


async def build(out_dir: str = "site", base_url: str = "", refresh: bool = True) -> dict:
    out = Path(out_dir)
    async with NewsHub() as hub:
        summary = await hub.refresh() if refresh else {}
        meta = {"updated_at": hub.last_refresh, "articles_indexed": len(hub.articles), "version": __version__}
        v1 = out / "v1"

        _write(v1 / "trending.json", {**meta, "stories": _stories(hub, limit=50)})
        for cat in CATEGORIES:
            _write(v1 / "trending" / f"{cat}.json", {**meta, "category": cat, "stories": _stories(hub, category=cat, limit=30)})
            _write(
                v1 / "feed" / f"{cat}.xml",
                stories_rss(hub.trending(category=cat, limit=30), f"FreeNews — trending {cat}", base_url),
            )
            total, arts = hub.headlines(category=cat, limit=100)
            _write(
                v1 / "headlines" / f"{cat}.json",
                {**meta, "category": cat, "total": total, "articles": [a.model_dump() for a in arts]},
            )
        for cc in hub.settings.countries:
            _write(
                v1 / "countries" / cc / "trending.json", {**meta, "country": cc, "stories": _stories(hub, country=cc, limit=30)}
            )
            total, arts = hub.headlines(country=cc, limit=100)
            _write(
                v1 / "countries" / cc / "headlines.json",
                {**meta, "country": cc, "total": total, "articles": [a.model_dump() for a in arts]},
            )
        total, arts = hub.headlines(limit=200)
        _write(v1 / "headlines.json", {**meta, "total": total, "articles": [a.model_dump() for a in arts]})
        _write(v1 / "trends.json", {**meta, **hub.trend_items()})
        _write(v1 / "sources.json", {**meta, "sources": [s.model_dump() for s in hub.feed_status()]})
        _write(v1 / "feed.xml", stories_rss(hub.trending(limit=50), "FreeNews — world trending news", base_url))
        _write(v1 / "meta.json", {**meta, "refresh": summary, "categories": CATEGORIES, "countries": hub.settings.countries})
        _write(out / "index.html", (STATIC / "index.html").read_text(encoding="utf-8").replace("__MODE__", "static"))
        _write(out / ".nojekyll", "")
    return {**meta, **summary, "out": str(out)}
