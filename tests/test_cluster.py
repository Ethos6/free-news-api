from datetime import datetime, timezone

from freenews.cluster import cluster_articles, outlet_key, tokens
from freenews.models import Article, SourceRef

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def art(i, title, domain, hours_ago=1.0, cat="world", related=0):
    ts = datetime.fromtimestamp(NOW.timestamp() - hours_ago * 3600, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return Article(
        id=f"a{i}",
        title=title,
        url=f"https://{domain}/{i}",
        source=SourceRef(id=domain, name=domain, domain=domain),
        category=cat,
        country="us",
        published_at=ts,
        related_count=related,
    )


def test_tokens():
    assert tokens("The President's new plan: what we know") == {"president", "plan"}
    assert "summit" in tokens("Summits")


def test_outlet_key_groups_domains():
    assert outlet_key(art(1, "x", "www.bbc.co.uk")) == "bbc"
    assert outlet_key(art(1, "x", "bbc.com")) == "bbc"
    assert outlet_key(art(1, "x", "edition.cnn.com")) == "cnn"


def test_same_event_is_clustered_and_ranked_first():
    arts = [
        art(1, "World leaders gather in Geneva for emergency climate summit", "bbc.com"),
        art(2, "Geneva climate summit: leaders gather for emergency talks", "theguardian.com"),
        art(3, "Emergency climate summit opens in Geneva as leaders arrive", "reuters.com"),
        art(4, "Local bakery wins national bread award", "localnews.com"),
        art(5, "Iceland volcano erupts, flights grounded across Europe", "apnews.com", 2),
        art(6, "Flights grounded across Europe after Iceland volcano erupts", "cnn.com", 2),
    ]
    stories = cluster_articles(arts, now=NOW)
    assert stories[0].sources_count == 3
    assert {a.id for a in stories[0].articles} == {"a1", "a2", "a3"}
    assert stories[1].sources_count == 2
    assert len(stories) == 3
    assert stories[0].score > stories[1].score > stories[2].score


def test_same_outlet_counts_once():
    arts = [
        art(1, "Geneva climate summit opens with leaders", "bbc.com"),
        art(2, "Geneva climate summit opens with world leaders", "bbc.co.uk"),
    ]
    s = cluster_articles(arts, now=NOW)[0]
    assert s.articles_count == 2 and s.sources_count == 1


def test_recency_decay_and_trend_boost():
    old = [art(1, "Old story about mars rover landing", "a.com", 30), art(2, "Mars rover landing old story", "b.com", 30)]
    new = [art(3, "Fresh story about ocean cleanup project", "c.com", 1), art(4, "Ocean cleanup project fresh story", "d.com", 1)]
    stories = cluster_articles(old + new, now=NOW)
    assert stories[0].articles[0].id in {"a3", "a4"}
    boosted = cluster_articles(old + new, now=NOW, trend_terms={"mars rover"})
    old_plain = next(s for s in stories if "mars" in s.keywords)
    old_boost = next(s for s in boosted if "mars" in s.keywords)
    assert old_boost.score > old_plain.score


def test_category_prefers_specific():
    arts = [
        art(1, "Chipmaker shares soar on record profits", "a.com", cat="top"),
        art(2, "Chipmaker shares soar after record profits", "b.com", cat="business"),
    ]
    assert cluster_articles(arts, now=NOW)[0].category == "business"
