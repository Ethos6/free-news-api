"""API data models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    id: str
    name: str
    domain: str | None = None


class Article(BaseModel):
    id: str
    title: str
    url: str
    description: str = ""
    source: SourceRef
    category: str
    country: str
    language: str = "en"
    published_at: str | None = Field(None, description="ISO 8601, UTC")
    image: str | None = None
    author: str | None = None
    related_count: int = Field(0, description="Other outlets Google News groups with this article")


class Story(BaseModel):
    """A trending story: the same event reported by several outlets, clustered together."""

    id: str
    title: str
    description: str = ""
    url: str
    image: str | None = None
    category: str
    score: float
    sources_count: int
    articles_count: int
    first_seen: str | None = None
    latest: str | None = None
    countries: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    articles: list[Article] = Field(default_factory=list)


class TrendItem(BaseModel):
    title: str
    source: str  # google_trends | wikipedia | hackernews
    traffic: str | None = None
    url: str | None = None
    description: str | None = None
    image: str | None = None
    news: list[dict] = Field(default_factory=list)


class FeedStatus(BaseModel):
    id: str
    name: str
    url: str
    category: str
    country: str
    ok: bool | None = None
    articles: int = 0
    last_fetch: str | None = None
    elapsed_ms: int | None = None
    error: str | None = None
