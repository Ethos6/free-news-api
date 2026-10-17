"""HTTP API: trending stories, headlines, search, trends, NewsAPI.org-compatible endpoints, RSS output."""

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from . import __version__
from .config import Settings
from .core import NewsHub
from .models import Article, Story
from .sources import CATEGORIES, GOOGLE_NEWS_EDITIONS

STATIC = Path(__file__).with_name("static")


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.hits: dict[str, list] = defaultdict(lambda: [0.0, 0])

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        w = self.hits[key]
        if now - w[0] >= 60:
            w[0], w[1] = now, 0
        w[1] += 1
        if len(self.hits) > 50000:
            self.hits.clear()
        return w[1] <= self.per_minute


def stories_rss(stories: list[Story], title: str, link: str) -> str:
    items = []
    for s in stories:
        pub = s.latest or s.first_seen
        date = format_datetime(datetime.fromisoformat(pub.replace("Z", "+00:00"))) if pub else ""
        desc = s.description or ""
        desc += f" — covered by {s.sources_count} outlets: {', '.join(s.sources[:8])}"
        items.append(
            f"<item><title>{escape(s.title)}</title><link>{escape(s.url)}</link>"
            f'<guid isPermaLink="false">{s.id}</guid><pubDate>{date}</pubDate>'
            f"<category>{escape(s.category)}</category><description>{escape(desc)}</description></item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>{escape(title)}</title><link>{escape(link)}</link>"
        "<description>World top trending news, clustered across outlets.</description>" + "".join(items) + "</channel></rss>"
    )


def newsapi_article(a: Article) -> dict[str, Any]:
    return {
        "source": {"id": a.source.id, "name": a.source.name},
        "author": a.author,
        "title": a.title,
        "description": a.description or None,
        "url": a.url,
        "urlToImage": a.image,
        "publishedAt": a.published_at,
        "content": a.description or None,
    }


def create_app(settings: Settings | None = None, hub: NewsHub | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    limiter = RateLimiter(settings.rate_limit)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.hub = hub or NewsHub(settings)
        if settings.background_refresh:
            app.state.hub.start()
        yield
        await app.state.hub.stop()

    app = FastAPI(
        title="FreeNews API",
        version=__version__,
        description=(
            "Free, self-hosted, unlimited API for the world's top trending news. Aggregates publisher RSS feeds and "
            "Google News editions, clusters the same story across outlets and ranks what is trending. "
            "Includes NewsAPI.org-compatible endpoints."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    async def auth(request: Request) -> None:
        h = request.headers
        token = None
        authz = h.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
        token = token or h.get("x-api-key") or request.query_params.get("apiKey") or request.query_params.get("api_key")
        if settings.api_keys and token not in settings.api_keys:
            raise HTTPException(401, "invalid or missing API key")
        if not limiter.allow(token or (request.client.host if request.client else "anon")):
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})

    def get_hub(request: Request) -> NewsHub:
        return request.app.state.hub

    Auth = Depends(auth)
    Hub = Annotated[NewsHub, Depends(get_hub)]
    Cat = Annotated[str | None, Query(description=f"One of: {', '.join(CATEGORIES)}")]
    Country = Annotated[
        str | None, Query(description="ISO country code(s), comma-separated, e.g. us,in. 'int' = international outlets")
    ]

    def check_category(category: str | None) -> None:
        if category and category not in CATEGORIES and category != "all":
            raise HTTPException(400, f"unknown category {category!r}; use one of {CATEGORIES}")

    def meta(hub_: NewsHub) -> dict[str, Any]:
        return {"updated_at": hub_.last_refresh, "articles_indexed": len(hub_.articles)}

    # ------------------------------------------------------------------ meta
    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8").replace("__MODE__", "live"))

    @app.get("/health", tags=["meta"])
    async def health(hub_: Hub) -> dict[str, Any]:
        return {"status": "ok", "version": __version__, **meta(hub_)}

    @app.get("/v1/sources", tags=["meta"], dependencies=[Auth])
    async def sources(hub_: Hub) -> dict[str, Any]:
        return {"sources": [s.model_dump() for s in hub_.feed_status()]}

    @app.get("/v1/categories", tags=["meta"])
    async def categories() -> dict[str, Any]:
        return {"categories": CATEGORIES, "countries": sorted(GOOGLE_NEWS_EDITIONS)}

    @app.post("/v1/refresh", tags=["meta"], dependencies=[Auth])
    async def refresh(hub_: Hub) -> dict[str, Any]:
        return await hub_.refresh()

    # ------------------------------------------------------------------ news
    @app.get("/v1/trending", tags=["news"], dependencies=[Auth])
    async def trending(
        hub_: Hub,
        category: Cat = None,
        country: Country = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        hours: Annotated[float | None, Query(ge=1, le=72, description="Look-back window")] = None,
        articles: Annotated[int, Query(ge=0, le=50, description="Articles to include per story")] = 5,
    ) -> dict[str, Any]:
        check_category(category)
        stories = hub_.trending(category=category, country=country, limit=limit, window_hours=hours)
        return {
            **meta(hub_),
            "count": len(stories),
            "stories": [s.model_copy(update={"articles": s.articles[:articles]}).model_dump() for s in stories],
        }

    @app.get("/v1/headlines", tags=["news"], dependencies=[Auth])
    async def headlines(
        hub_: Hub,
        category: Cat = None,
        country: Country = None,
        source: Annotated[str | None, Query(description="Source id, outlet name or domain (comma-separated)")] = None,
        language: str | None = None,
        q: str | None = None,
        since: Annotated[str | None, Query(description="ISO date/time, e.g. 2026-10-17T00:00:00Z")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> dict[str, Any]:
        check_category(category)
        total, arts = hub_.headlines(
            category=category,
            country=country,
            source=source,
            language=language,
            q=q,
            since=since,
            limit=limit,
            offset=(page - 1) * limit,
        )
        return {**meta(hub_), "total": total, "page": page, "articles": [a.model_dump() for a in arts]}

    @app.get("/v1/search", tags=["news"], dependencies=[Auth])
    async def search(
        hub_: Hub,
        q: Annotated[str, Query(min_length=1, max_length=300)],
        country: str = "us",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        live: bool = True,
    ) -> dict[str, Any]:
        arts = await hub_.search(q, limit=limit, country=country, live=live)
        return {"query": q, "count": len(arts), "articles": [a.model_dump() for a in arts]}

    @app.get("/v1/trends", tags=["news"], dependencies=[Auth])
    async def trends(hub_: Hub, geo: str | None = None) -> dict[str, Any]:
        return {**meta(hub_), **hub_.trend_items(geo)}

    @app.get("/v1/feed.xml", tags=["news"], dependencies=[Auth])
    async def feed(request: Request, hub_: Hub, category: Cat = None, country: Country = None, limit: int = 30) -> Response:
        check_category(category)
        stories = hub_.trending(category=category, country=country, limit=min(limit, 100))
        title = "FreeNews — trending" + (f" {category}" if category else "") + (f" ({country})" if country else "")
        return Response(stories_rss(stories, title, str(request.base_url)), media_type="application/rss+xml")

    # ------------------------------------------------------------------ NewsAPI.org-compatible
    @app.get("/v2/top-headlines", tags=["compat: NewsAPI.org"], dependencies=[Auth])
    async def newsapi_top(
        hub_: Hub,
        country: str | None = None,
        category: str | None = None,
        sources: str | None = None,
        q: str | None = None,
        pageSize: Annotated[int, Query(ge=1, le=100)] = 20,  # noqa: N803
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> dict[str, Any]:
        cat = {"general": "top"}.get(category or "", category)
        check_category(cat)
        total, arts = hub_.headlines(
            category=cat or "top", country=country, source=sources, q=q, limit=pageSize, offset=(page - 1) * pageSize
        )
        return {"status": "ok", "totalResults": total, "articles": [newsapi_article(a) for a in arts]}

    @app.get("/v2/everything", tags=["compat: NewsAPI.org"], dependencies=[Auth])
    async def newsapi_everything(
        hub_: Hub,
        q: Annotated[str, Query(min_length=1)],
        language: str | None = None,
        sortBy: str = "publishedAt",  # noqa: N803
        pageSize: Annotated[int, Query(ge=1, le=100)] = 20,  # noqa: N803
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> dict[str, Any]:
        arts = await hub_.search(q, limit=100)
        if language:
            arts = [a for a in arts if a.language == language]
        start = (page - 1) * pageSize
        return {
            "status": "ok",
            "totalResults": len(arts),
            "articles": [newsapi_article(a) for a in arts[start : start + pageSize]],
        }

    @app.get("/v2/top-headlines/sources", tags=["compat: NewsAPI.org"], dependencies=[Auth])
    async def newsapi_sources(hub_: Hub) -> dict[str, Any]:
        seen = {}
        for s in hub_.sources:
            if s.kind == "rss":
                seen.setdefault(
                    s.id,
                    {
                        "id": s.id,
                        "name": s.name,
                        "description": "",
                        "url": s.url,
                        "category": s.category,
                        "language": s.language,
                        "country": s.country,
                    },
                )
        return {"status": "ok", "sources": list(seen.values())}

    return app


app = create_app()
