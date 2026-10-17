"""News sources: publisher RSS/Atom feeds plus Google News editions.

Every source is a public feed published by the outlet for exactly this purpose
(syndication). Add your own in a YAML/JSON file via FREENEWS_EXTRA_SOURCES.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

CATEGORIES = ["top", "world", "business", "technology", "science", "health", "sports", "entertainment"]


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    category: str
    country: str = "int"  # ISO 3166-1 alpha-2 (lowercase) or "int" for international outlets
    language: str = "en"
    weight: float = 1.0  # editorial weight used by the trending score
    kind: str = "rss"  # rss | google_news

    def as_dict(self) -> dict:
        return asdict(self)


def _s(id, name, url, category, country="int", language="en", weight=1.0):  # noqa: A002
    return Source(id, name, url, category, country, language, weight)


PUBLISHER_FEEDS: list[Source] = [
    # ---- world / top
    _s("bbc-world", "BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", "world", "gb", weight=1.3),
    _s("bbc-top", "BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "top", "gb", weight=1.3),
    _s("guardian-world", "The Guardian", "https://www.theguardian.com/world/rss", "world", "gb", weight=1.2),
    _s("nyt-world", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "world", "us", weight=1.3),
    _s("nyt-home", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "top", "us", weight=1.3),
    _s("npr-world", "NPR", "https://feeds.npr.org/1004/rss.xml", "world", "us", weight=1.1),
    _s("npr-news", "NPR", "https://feeds.npr.org/1001/rss.xml", "top", "us", weight=1.1),
    _s("dw-world", "DW", "https://rss.dw.com/xml/rss-en-world", "world", "de", weight=1.1),
    _s("aljazeera", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "world", "qa", weight=1.1),
    _s("france24", "France 24", "https://www.france24.com/en/rss", "world", "fr", weight=1.1),
    _s("sky-world", "Sky News", "https://feeds.skynews.com/feeds/rss/world.xml", "world", "gb"),
    _s("cbc-world", "CBC News", "https://www.cbc.ca/webfeed/rss/rss-world", "world", "ca"),
    _s("abc-au", "ABC News (Australia)", "https://www.abc.net.au/news/feed/51120/rss.xml", "top", "au"),
    _s("cbs-world", "CBS News", "https://www.cbsnews.com/latest/rss/world", "world", "us"),
    _s("abcnews-intl", "ABC News", "https://abcnews.go.com/abcnews/internationalheadlines", "world", "us"),
    _s("fox-world", "Fox News", "https://moxie.foxnews.com/google-publisher/world.xml", "world", "us", weight=0.9),
    _s("wapo-world", "The Washington Post", "https://feeds.washingtonpost.com/rss/world", "world", "us", weight=1.2),
    _s("independent-world", "The Independent", "https://www.independent.co.uk/news/world/rss", "world", "gb"),
    _s("euronews", "Euronews", "https://www.euronews.com/rss?format=mrss&level=theme&name=news", "world", "int"),
    _s("toi-top", "The Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "top", "in"),
    _s("thehindu-intl", "The Hindu", "https://www.thehindu.com/news/international/feeder/default.rss", "world", "in"),
    _s("ndtv-world", "NDTV", "https://feeds.feedburner.com/ndtvnews-world-news", "world", "in"),
    _s("scmp-world", "South China Morning Post", "https://www.scmp.com/rss/91/feed", "world", "hk"),
    _s("japantimes", "The Japan Times", "https://www.japantimes.co.jp/feed/", "top", "jp"),
    _s("un-news", "UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml", "world", "int", weight=0.8),
    _s("politico", "Politico", "https://rss.politico.com/politics-news.xml", "top", "us"),
    # ---- business
    _s("cnbc-top", "CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "business", "us", weight=1.1),
    _s("cnbc-world", "CNBC", "https://www.cnbc.com/id/100727362/device/rss/rss.html", "business", "us"),
    _s("marketwatch", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "business", "us"),
    _s("bbc-business", "BBC News", "https://feeds.bbci.co.uk/news/business/rss.xml", "business", "gb", weight=1.2),
    _s("guardian-business", "The Guardian", "https://www.theguardian.com/business/rss", "business", "gb"),
    _s(
        "nyt-business",
        "The New York Times",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
        "business",
        "us",
        weight=1.2,
    ),
    # ---- technology
    _s("techcrunch", "TechCrunch", "https://techcrunch.com/feed/", "technology", "us", weight=1.1),
    _s("theverge", "The Verge", "https://www.theverge.com/rss/index.xml", "technology", "us", weight=1.1),
    _s("arstechnica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "technology", "us", weight=1.1),
    _s("wired", "Wired", "https://www.wired.com/feed/rss", "technology", "us"),
    _s("engadget", "Engadget", "https://www.engadget.com/rss.xml", "technology", "us"),
    _s("bbc-tech", "BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml", "technology", "gb", weight=1.2),
    _s(
        "nyt-tech",
        "The New York Times",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "technology",
        "us",
        weight=1.2,
    ),
    _s("hackernews", "Hacker News", "https://hnrss.org/frontpage", "technology", "int", weight=0.8),
    # ---- science
    _s("sciencedaily", "ScienceDaily", "https://www.sciencedaily.com/rss/top/science.xml", "science", "us"),
    _s("nasa", "NASA", "https://www.nasa.gov/news-release/feed/", "science", "us"),
    _s("bbc-science", "BBC News", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "science", "gb", weight=1.2),
    _s(
        "nyt-science",
        "The New York Times",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
        "science",
        "us",
        weight=1.2,
    ),
    _s("guardian-science", "The Guardian", "https://www.theguardian.com/science/rss", "science", "gb"),
    # ---- health
    _s("bbc-health", "BBC News", "https://feeds.bbci.co.uk/news/health/rss.xml", "health", "gb", weight=1.2),
    _s("npr-health", "NPR", "https://feeds.npr.org/1128/rss.xml", "health", "us"),
    _s("nyt-health", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml", "health", "us", weight=1.2),
    # ---- sports
    _s("espn", "ESPN", "https://www.espn.com/espn/rss/news", "sports", "us", weight=1.1),
    _s("bbc-sport", "BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "sports", "gb", weight=1.2),
    _s("guardian-sport", "The Guardian", "https://www.theguardian.com/sport/rss", "sports", "gb"),
    # ---- entertainment
    _s("bbc-ent", "BBC News", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "entertainment", "gb", weight=1.2),
    _s("variety", "Variety", "https://variety.com/feed/", "entertainment", "us"),
    _s("nyt-arts", "The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml", "entertainment", "us"),
]

# Google News editions: (country, hl, gl, ceid)
GOOGLE_NEWS_EDITIONS: dict[str, tuple[str, str, str]] = {
    "us": ("en-US", "US", "US:en"),
    "gb": ("en-GB", "GB", "GB:en"),
    "in": ("en-IN", "IN", "IN:en"),
    "ca": ("en-CA", "CA", "CA:en"),
    "au": ("en-AU", "AU", "AU:en"),
    "ie": ("en-IE", "IE", "IE:en"),
    "nz": ("en-NZ", "NZ", "NZ:en"),
    "sg": ("en-SG", "SG", "SG:en"),
    "za": ("en-ZA", "ZA", "ZA:en"),
    "ng": ("en-NG", "NG", "NG:en"),
    "ke": ("en-KE", "KE", "KE:en"),
    "pk": ("en-PK", "PK", "PK:en"),
    "ph": ("en-PH", "PH", "PH:en"),
    "my": ("en-MY", "MY", "MY:en"),
    "ae": ("en-AE", "AE", "AE:en"),
    "de": ("de", "DE", "DE:de"),
    "fr": ("fr", "FR", "FR:fr"),
    "es": ("es", "ES", "ES:es"),
    "it": ("it", "IT", "IT:it"),
    "br": ("pt-BR", "BR", "BR:pt-419"),
    "mx": ("es-419", "MX", "MX:es-419"),
    "jp": ("ja", "JP", "JP:ja"),
    "kr": ("ko", "KR", "KR:ko"),
}

GOOGLE_TOPICS = {
    "world": "WORLD",
    "business": "BUSINESS",
    "technology": "TECHNOLOGY",
    "science": "SCIENCE",
    "health": "HEALTH",
    "sports": "SPORTS",
    "entertainment": "ENTERTAINMENT",
}


def google_news_sources(countries: list[str]) -> list[Source]:
    out: list[Source] = []
    for cc in countries:
        cc = cc.lower()
        if cc not in GOOGLE_NEWS_EDITIONS:
            continue
        hl, gl, ceid = GOOGLE_NEWS_EDITIONS[cc]
        lang = hl.split("-")[0]
        q = f"hl={hl}&gl={gl}&ceid={ceid}"
        out.append(
            Source(
                f"gnews-{cc}-top", f"Google News {gl}", f"https://news.google.com/rss?{q}", "top", cc, lang, 1.0, "google_news"
            )
        )
        for cat, topic in GOOGLE_TOPICS.items():
            out.append(
                Source(
                    f"gnews-{cc}-{cat}",
                    f"Google News {gl}",
                    f"https://news.google.com/rss/headlines/section/topic/{topic}?{q}",
                    cat,
                    cc,
                    lang,
                    1.0,
                    "google_news",
                )
            )
    return out


def load_sources(countries: list[str], include_publishers: bool = True, extra_path: str | None = None) -> list[Source]:
    sources = list(PUBLISHER_FEEDS) if include_publishers else []
    sources += google_news_sources(countries)
    extra_path = extra_path or os.getenv("FREENEWS_EXTRA_SOURCES")
    if extra_path and os.path.isfile(extra_path):
        with open(extra_path, encoding="utf-8") as fh:
            for item in json.load(fh):
                sources.append(Source(**item))
    disabled = {x.strip() for x in os.getenv("FREENEWS_DISABLED_SOURCES", "").split(",") if x.strip()}
    return [s for s in sources if s.id not in disabled]
