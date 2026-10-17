"""NewsHub: polls every feed, keeps a rolling window of articles, computes trending stories."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

from curl_cffi.requests import AsyncSession

from .cluster import cluster_articles, tokens
from .config import Settings
from .models import Article, FeedStatus, Story, TrendItem
from .parse import parse_feed
from .sources import GOOGLE_NEWS_EDITIONS, Source, load_sources
from .trends import google_trends_url, parse_google_trends, parse_wikipedia_mostread, wikipedia_mostread_url

log = logging.getLogger("freenews")
UA_NOTE = "FreeNewsAPI/1.0 (+https://github.com/Ethos6/free-news-api)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class NewsHub:
    def __init__(self, settings: Settings | None = None, sources: list[Source] | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.sources = sources if sources is not None else load_sources(self.settings.countries, self.settings.include_publishers)
        self.source_by_id = {s.id: s for s in self.sources}
        self.weights = {s.id: s.weight for s in self.sources}
        self.articles: dict[str, Article] = {}
        self.status: dict[str, FeedStatus] = {
            s.id: FeedStatus(id=s.id, name=s.name, url=s.url, category=s.category, country=s.country) for s in self.sources
        }
        self.trends: dict[str, list[TrendItem]] = {}
        self.wikipedia: list[TrendItem] = []
        self.last_refresh: str | None = None
        self._validators: dict[str, tuple[str | None, str | None]] = {}
        self._session: AsyncSession | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._version = 0
        self._story_cache: dict[tuple, tuple[int, list[Story]]] = {}
        self._load_snapshot()

    # ------------------------------------------------------------------ http
    def _http(self) -> AsyncSession:
        if self._session is None:
            proxy = random.choice(self.settings.proxies) if self.settings.proxies else None
            self._session = AsyncSession(impersonate="chrome", timeout=self.settings.timeout, proxy=proxy)
        return self._session

    async def _get(self, url: str, headers: dict | None = None):
        return await self._http().get(url, headers=headers or {}, allow_redirects=True)

    # ------------------------------------------------------------------ refresh
    async def _fetch_source(self, source: Source, sem: asyncio.Semaphore) -> list[Article]:
        st = self.status[source.id]
        etag, modified = self._validators.get(source.id, (None, None))
        headers = {"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"}
        if etag:
            headers["If-None-Match"] = etag
        if modified:
            headers["If-Modified-Since"] = modified
        async with sem:
            start = time.perf_counter()
            try:
                resp = await self._get(source.url, headers)
            except Exception as exc:  # noqa: BLE001
                st.ok, st.error = False, f"{type(exc).__name__}: {str(exc)[:150]}"
                st.elapsed_ms = int((time.perf_counter() - start) * 1000)
                st.last_fetch = _iso(_now())
                return []
        st.elapsed_ms = int((time.perf_counter() - start) * 1000)
        st.last_fetch = _iso(_now())
        if resp.status_code == 304:
            st.ok, st.error = True, None
            return []
        if resp.status_code >= 400:
            st.ok, st.error = False, f"HTTP {resp.status_code}"
            return []
        arts = await asyncio.to_thread(parse_feed, resp.content, source)
        if not arts:
            st.ok, st.error = False, "no items parsed"
            return []
        self._validators[source.id] = (resp.headers.get("etag"), resp.headers.get("last-modified"))
        st.ok, st.error, st.articles = True, None, len(arts)
        return arts

    async def _fetch_trends(self) -> None:
        async def geo(g: str) -> None:
            try:
                r = await self._get(google_trends_url(g))
                if r.status_code == 200:
                    items = parse_google_trends(r.content)
                    if items:
                        self.trends[g.upper()] = items
            except Exception as exc:  # noqa: BLE001
                log.info("google trends %s failed: %s", g, exc)

        async def wiki() -> None:
            for days_back in (1, 2):
                try:
                    day = _now() - timedelta(days=days_back)
                    r = await self._get(wikipedia_mostread_url("en", day), {"User-Agent": UA_NOTE, "Api-User-Agent": UA_NOTE})
                    items = parse_wikipedia_mostread(r.content) if r.status_code == 200 else []
                    if items:
                        self.wikipedia = items
                        return
                except Exception as exc:  # noqa: BLE001
                    log.info("wikipedia most-read failed: %s", exc)

        await asyncio.gather(*(geo(g) for g in self.settings.trend_geos), wiki())

    async def refresh(self) -> dict:
        async with self._lock:
            started = time.perf_counter()
            sem = asyncio.Semaphore(self.settings.concurrency)
            results = await asyncio.gather(*(self._fetch_source(s, sem) for s in self.sources), self._fetch_trends())
            now = _now()
            new = 0
            for arts in results[:-1]:
                for a in arts:
                    if a.published_at is None:
                        a.published_at = _iso(now)
                    cur = self.articles.get(a.id)
                    if cur is None:
                        self.articles[a.id] = a
                        new += 1
                    else:
                        # keep the most specific category and the richest data
                        if cur.category == "top" and a.category != "top":
                            cur.category = a.category
                        cur.related_count = max(cur.related_count, a.related_count)
                        cur.image = cur.image or a.image
                        cur.description = cur.description or a.description
            self._prune(now)
            self.last_refresh = _iso(now)
            self._version += 1
            self._story_cache.clear()
            ok = sum(1 for s in self.status.values() if s.ok)
            summary = {
                "new_articles": new,
                "total_articles": len(self.articles),
                "feeds_ok": ok,
                "feeds_total": len(self.sources),
                "seconds": round(time.perf_counter() - started, 2),
            }
            log.info("refresh: %s", summary)
            self._save_snapshot()
            return summary

    def _prune(self, now: datetime) -> None:
        cutoff = _iso(now - timedelta(hours=self.settings.retention_hours))
        self.articles = {k: a for k, a in self.articles.items() if (a.published_at or "") >= cutoff}

    async def _loop(self) -> None:
        while True:
            try:
                await self.refresh()
            except Exception:  # noqa: BLE001
                log.exception("refresh failed")
            await asyncio.sleep(max(self.settings.refresh_minutes, 1) * 60)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> NewsHub:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    # ------------------------------------------------------------------ snapshot
    def _load_snapshot(self) -> None:
        path = self.settings.snapshot_path
        if not path or not Path(path).is_file():
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            for raw in data.get("articles", []):
                a = Article.model_validate(raw)
                self.articles[a.id] = a
            self.last_refresh = data.get("last_refresh")
            self._prune(_now())
        except Exception:  # noqa: BLE001
            log.warning("could not load snapshot %s", path)

    def _save_snapshot(self) -> None:
        path = self.settings.snapshot_path
        if not path:
            return
        try:
            tmp = Path(path + ".tmp")
            tmp.write_text(
                json.dumps({"last_refresh": self.last_refresh, "articles": [a.model_dump() for a in self.articles.values()]}),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError:
            log.warning("could not save snapshot %s", path)

    # ------------------------------------------------------------------ queries
    def trend_terms(self) -> set[str]:
        terms = {t.title.lower() for items in self.trends.values() for t in items}
        terms |= {t.title.lower() for t in self.wikipedia[:15]}
        return {t for t in terms if len(t) >= 4}

    def _filter(
        self,
        category: str | None = None,
        country: str | None = None,
        source: str | None = None,
        language: str | None = None,
        q: str | None = None,
        since: str | None = None,
    ) -> list[Article]:
        arts = list(self.articles.values())
        if category and category != "all":
            if category == "top":
                arts = [a for a in arts if a.category in ("top", "world")]
            else:
                arts = [a for a in arts if a.category == category]
        if country:
            cc = {c.strip().lower() for c in country.split(",")}
            arts = [a for a in arts if a.country in cc or (a.country == "int" and "int" in cc)]
        if source:
            ids = {s.strip().lower() for s in source.split(",")}
            arts = [
                a for a in arts if a.source.id.lower() in ids or (a.source.domain or "") in ids or a.source.name.lower() in ids
            ]
        if language:
            arts = [a for a in arts if a.language == language.lower()]
        if since:
            arts = [a for a in arts if (a.published_at or "") >= since]
        if q:
            words = tokens(q) or {q.lower()}
            arts = [a for a in arts if words <= tokens(f"{a.title} {a.description}") or q.lower() in a.title.lower()]
        return arts

    def headlines(self, *, limit: int = 50, offset: int = 0, **filters) -> tuple[int, list[Article]]:
        arts = sorted(self._filter(**filters), key=lambda a: a.published_at or "", reverse=True)
        return len(arts), arts[offset : offset + limit]

    def trending(
        self, *, category: str | None = None, country: str | None = None, limit: int = 20, window_hours: float | None = None
    ) -> list[Story]:
        key = (category, country, window_hours)
        cached = self._story_cache.get(key)
        if cached and cached[0] == self._version:
            return cached[1][:limit]
        window = window_hours or self.settings.trending_window_hours
        since = _iso(_now() - timedelta(hours=window))
        arts = self._filter(country=country, since=since)
        stories = cluster_articles(
            arts, weights=self.weights, trend_terms=self.trend_terms(), half_life_hours=self.settings.half_life_hours
        )
        if category and category not in ("all", "top"):
            stories = [s for s in stories if s.category == category]
        self._story_cache[key] = (self._version, stories)
        return stories[:limit]

    def trend_items(self, geo: str | None = None) -> dict:
        order = [g.upper() for g in self.settings.trend_geos]
        geos = [geo.upper()] if geo else [g for g in order if g in self.trends] + [g for g in self.trends if g not in order]
        return {
            "google_trends": {g: [t.model_dump() for t in self.trends.get(g, [])] for g in geos},
            "wikipedia_most_read": [t.model_dump() for t in self.wikipedia],
        }

    async def search(self, q: str, *, limit: int = 30, country: str = "us", live: bool = True) -> list[Article]:
        """Search the local index plus live Google News + Bing News results for any query."""
        local = self._filter(q=q)
        found: dict[str, Article] = {a.id: a for a in local}
        if live:
            cc = country.lower() if country.lower() in GOOGLE_NEWS_EDITIONS else "us"
            hl, gl, ceid = GOOGLE_NEWS_EDITIONS[cc]
            lang = hl.split("-")[0]
            gsrc = Source("gnews-search", f"Google News {gl}", "", "top", cc, lang, 1.0, "google_news")
            bsrc = Source("bing-news", "Bing News", "", "top", cc, lang, 1.0, "bing_news")
            urls = [
                (gsrc, f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={ceid}"),
                (bsrc, f"https://www.bing.com/news/search?q={quote_plus(q)}&format=rss&setlang={lang}&cc={cc}"),
            ]

            async def one(src: Source, url: str) -> list[Article]:
                try:
                    r = await self._get(url)
                    return parse_feed(r.content, src) if r.status_code == 200 else []
                except Exception:  # noqa: BLE001
                    return []

            for arts in await asyncio.gather(*(one(s, u) for s, u in urls)):
                for a in arts:
                    found.setdefault(a.id, a)
        return sorted(found.values(), key=lambda a: a.published_at or "", reverse=True)[:limit]

    def feed_status(self) -> list[FeedStatus]:
        return list(self.status.values())
