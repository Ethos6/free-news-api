from datetime import datetime, timezone

from conftest import SOURCES, fixture

from freenews.parse import canonical_url, clean_text, parse_feed
from freenews.sources import Source, google_news_sources, load_sources
from freenews.trends import parse_google_trends, parse_wikipedia_mostread


def test_rss_with_media_thumbnail():
    arts = parse_feed(fixture("bbc.xml"), SOURCES[0])
    assert len(arts) == 2
    a = arts[0]
    assert a.title == "Global leaders gather in Geneva for emergency climate summit"
    assert a.description == "Leaders from 40 countries meet to agree emissions cuts."
    assert a.image == "https://ichef.bbci.co.uk/img1.jpg"
    assert a.published_at == "2026-10-17T09:58:17Z"
    assert a.source.domain == "bbc.com"
    assert a.category == "world" and a.country == "gb"


def test_tracking_params_do_not_change_id():
    a = parse_feed(fixture("bbc.xml"), SOURCES[0])[0]
    assert "at_medium" not in canonical_url(a.url)


def test_rss_media_content_and_author():
    a = parse_feed(fixture("guardian.xml"), SOURCES[1])[0]
    assert a.image == "https://i.guim.co.uk/img2.jpg"
    assert a.author == "Jane Doe"


def test_atom_feed_and_inline_image():
    a = parse_feed(fixture("verge.atom"), SOURCES[2], now=datetime(2030, 1, 1, tzinfo=timezone.utc))[0]
    assert a.url == "https://www.theverge.com/ai/1"
    assert a.image == "https://cdn.vox-cdn.com/x.jpg"
    assert a.published_at == "2026-10-17T15:00:00Z"  # converted to UTC
    assert a.author == "Alex Writer"


def test_google_news_publisher_and_related():
    arts = parse_feed(fixture("gnews.xml"), SOURCES[3])
    a = arts[0]
    assert a.title == "World leaders gather in Geneva for emergency climate summit"
    assert a.source.name == "Reuters" and a.source.domain == "reuters.com"
    assert a.related_count == 2
    assert a.description == ""


def test_bing_news_unwraps_link():
    src = Source("bing-news", "Bing News", "", "top", "us", kind="bing_news")
    a = parse_feed(fixture("bing_news.xml"), src)[0]
    assert a.url == "https://www.example.com/climate"
    assert a.source.name == "Example Times"


def test_google_trends():
    items = parse_google_trends(fixture("trends.xml"))
    assert items[0].title == "hull city" and items[0].traffic == "200+"
    assert [n["source"] for n in items[0].news] == ["Diario AS", "Fubo"]
    assert items[0].url == "https://as.com/a"
    assert parse_google_trends(b"not xml") == []


def test_wikipedia_mostread_skips_special_pages():
    items = parse_wikipedia_mostread(fixture("wikipedia_featured.json"))
    assert [i.title for i in items] == ["GBU-43/B MOAB", "Katie Zacharia"]
    assert items[0].traffic == "453,110 views"


def test_clean_text_truncates():
    assert clean_text("<p>a &amp; b</p>") == "a & b"
    assert len(clean_text("word " * 500, 50)) <= 50


def test_sources(monkeypatch):
    g = google_news_sources(["us", "zz"])
    assert len(g) == 8 and all(s.kind == "google_news" for s in g)
    monkeypatch.setenv("FREENEWS_DISABLED_SOURCES", "bbc-world")
    ids = {s.id for s in load_sources(["us"])}
    assert "bbc-world" not in ids and "guardian-world" in ids
    all_ids = [s.id for s in load_sources(["us", "gb"])]
    assert len(all_ids) == len(set(all_ids)), "source ids must be unique"


def test_future_dates_are_clamped():
    now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
    a = parse_feed(fixture("bbc.xml"), SOURCES[0], now=now)[0]
    assert a.published_at == "2026-10-17T09:00:00Z"
