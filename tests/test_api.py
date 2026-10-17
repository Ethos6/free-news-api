import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from freenews.api import create_app


@pytest.fixture
def client(hub, settings):
    with TestClient(create_app(settings, hub=hub)) as c:
        yield c


def test_health_and_ui(client):
    assert client.get("/health").json()["status"] == "ok"
    html = client.get("/").text
    assert "FreeNews" in html and '"live"' in html
    assert client.get("/openapi.json").status_code == 200


def test_trending_clusters_across_outlets(client):
    body = client.get("/v1/trending").json()
    top = body["stories"][0]
    assert "Geneva" in top["title"]
    assert top["sources_count"] == 3  # BBC + Guardian + Reuters (via Google News)
    assert top["url"].startswith("https://www.")  # a direct publisher link is preferred over news.google.com
    assert top["image"]
    assert body["updated_at"] == "2026-10-17T12:00:00Z"


def test_trending_filters(client):
    tech = client.get("/v1/trending", params={"category": "technology"}).json()["stories"]
    assert tech and all(s["category"] == "technology" for s in tech)
    assert client.get("/v1/trending", params={"category": "nope"}).status_code == 400
    gb = client.get("/v1/trending", params={"country": "gb"}).json()["stories"]
    assert all("gb" in s["countries"] for s in gb)


def test_headlines(client):
    body = client.get("/v1/headlines", params={"limit": 3}).json()
    assert body["total"] == 7 and len(body["articles"]) == 3
    dates = [a["published_at"] for a in body["articles"]]
    assert dates == sorted(dates, reverse=True)
    q = client.get("/v1/headlines", params={"q": "volcano"}).json()
    assert q["total"] == 2
    src = client.get("/v1/headlines", params={"source": "The Guardian"}).json()
    assert src["total"] == 2


def test_search_local_only(client):
    body = client.get("/v1/search", params={"q": "climate summit", "live": "false"}).json()
    assert body["count"] >= 2


def test_trends_and_sources(client):
    t = client.get("/v1/trends").json()
    assert t["google_trends"]["US"][0]["title"] == "hull city"
    assert t["wikipedia_most_read"][0]["title"] == "GBU-43/B MOAB"
    assert len(client.get("/v1/sources").json()["sources"]) == 4


def test_rss_output(client):
    r = client.get("/v1/feed.xml")
    assert r.headers["content-type"].startswith("application/rss+xml")
    assert "<rss" in r.text and "Geneva" in r.text


def test_newsapi_compat(client):
    body = client.get("/v2/top-headlines", params={"pageSize": 2}).json()
    assert body["status"] == "ok" and body["totalResults"] >= 2
    a = body["articles"][0]
    assert set(a) == {"source", "author", "title", "description", "url", "urlToImage", "publishedAt", "content"}
    biz = client.get("/v2/top-headlines", params={"category": "general"}).json()
    assert biz["status"] == "ok"
    srcs = client.get("/v2/top-headlines/sources").json()
    assert srcs["sources"][0]["id"] == "bbc-world"


def test_api_keys_and_rate_limit(hub, settings):
    settings.api_keys = ["k1"]
    settings.rate_limit = 2
    with TestClient(create_app(settings, hub=hub)) as c:
        assert c.get("/v1/trending").status_code == 401
        assert c.get("/v1/trending", params={"apiKey": "k1"}).status_code == 200
        assert c.get("/v1/trending", headers={"X-Api-Key": "k1"}).status_code == 200
        assert c.get("/v1/trending", headers={"Authorization": "Bearer k1"}).status_code == 429
        assert c.get("/health").status_code == 200


def test_static_build(hub, tmp_path, monkeypatch):
    import freenews.static_build as sb

    class Ctx:
        async def __aenter__(self):
            return hub

        async def __aexit__(self, *a):
            return None

    monkeypatch.setattr(sb, "NewsHub", lambda: Ctx())
    asyncio.run(sb.build(str(tmp_path), refresh=False))
    data = json.loads((tmp_path / "v1" / "trending.json").read_text())
    assert data["stories"][0]["sources_count"] == 3
    assert (tmp_path / "v1" / "trending" / "technology.json").exists()
    assert (tmp_path / "v1" / "headlines" / "world.json").exists()
    assert (tmp_path / "v1" / "feed.xml").read_text().startswith("<?xml")
    assert '"static"' in (tmp_path / "index.html").read_text()
    assert (tmp_path / ".nojekyll").exists()
