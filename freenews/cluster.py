"""Trending detection.

A story is "trending" when many independent outlets publish it at about the same
time. We cluster headlines from every feed by weighted word overlap, then score
each cluster by how many distinct outlets cover it, how important those outlets
are, how fresh it is, and whether people are searching for it (Google Trends /
Wikipedia most-read).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .models import Article, Story

STOPWORDS = set(
    """a about above after again against all also am an and any are as at be because been before being below between both
    but by can could did do does doing down during each few for from further had has have having he her here hers herself
    him himself his how i if in into is it its itself just me more most my myself no nor not now of off on once only or
    other our ours ourselves out over own same she should so some such than that the their theirs them themselves then
    there these they this those through to too under until up very was we were what when where which while who whom why
    will with would you your yours yourself yourselves says said say new news live latest update updates breaking report
    reports reported video watch photos how why what amid over after year years day days week weeks first one two three
    may might us vs via get gets got make makes made back still could top best big world know need here's what's""".split()
)
_TOKEN = re.compile(r"[\w][\w'’-]*", re.UNICODE)
SECOND_LEVEL = {"co", "com", "org", "net", "ac", "gov", "edu", "ne", "or"}


def tokens(text: str) -> set[str]:
    out = set()
    for raw in _TOKEN.findall(text.lower()):
        t = raw.strip("'’-").replace("’", "'")
        if t.endswith("'s"):
            t = t[:-2]
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        if (len(t) >= 3 or t.isdigit()) and t not in STOPWORDS:
            out.add(t)
    return out


def outlet_key(article: Article) -> str:
    """bbc.co.uk / feeds.bbci.co.uk / bbc.com -> 'bbc' so one outlet counts once."""
    host = article.source.domain or ""
    parts = [p for p in host.split(".") if p and p != "www"]
    if len(parts) >= 3 and parts[-2] in SECOND_LEVEL:
        name = parts[-3]
    elif len(parts) >= 2:
        name = parts[-2]
    else:
        name = article.source.name.lower()
    name = name.removesuffix("i") if name == "bbci" else name
    return name or article.source.name.lower()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def cluster_articles(
    articles: list[Article],
    *,
    weights: dict[str, float] | None = None,
    trend_terms: set[str] | None = None,
    now: datetime | None = None,
    half_life_hours: float = 8.0,
    threshold: float = 0.5,
) -> list[Story]:
    now = now or datetime.now(timezone.utc)
    weights = weights or {}
    trend_terms = {t.lower() for t in (trend_terms or set())}
    toks = [tokens(a.title) for a in articles]

    # IDF over this batch of headlines
    df: Counter[str] = Counter()
    for t in toks:
        df.update(t)
    n = max(len(articles), 1)
    idf = {w: math.log(1 + n / c) for w, c in df.items()}

    def weight(ts: set[str]) -> float:
        return sum(idf.get(w, 0.0) for w in ts)

    order = sorted(range(len(articles)), key=lambda i: articles[i].published_at or "", reverse=True)
    cluster_of: dict[int, int] = {}
    members: dict[int, list[int]] = defaultdict(list)
    index: dict[str, list[int]] = defaultdict(list)

    for i in order:
        ti = toks[i]
        if not ti:
            continue
        shared_counts: Counter[int] = Counter()
        for w in ti:
            for j in index.get(w, ()):
                shared_counts[j] += 1
        best, best_sim = None, 0.0
        wi = weight(ti)
        for j, cnt in shared_counts.items():
            if cnt < 2:
                continue
            shared = ti & toks[j]
            sim = weight(shared) / max(min(wi, weight(toks[j])), 1e-9)
            if sim > best_sim:
                best, best_sim = j, sim
        cid = cluster_of[best] if best is not None and best_sim >= threshold else i
        cluster_of[i] = cid
        members[cid].append(i)
        for w in ti:
            index[w].append(i)

    stories: list[Story] = []
    for idxs in members.values():
        arts = [articles[i] for i in idxs]
        outlets: dict[str, float] = {}
        for a in arts:
            key = outlet_key(a)
            outlets[key] = max(outlets.get(key, 0.0), weights.get(a.source.id, 1.0))
        related = sum(min(a.related_count, 10) for a in arts)
        times = [t for t in (_parse_time(a.published_at) for a in arts) if t]
        latest = max(times) if times else now
        first = min(times) if times else now
        age_h = max((now - latest).total_seconds() / 3600, 0.0)
        decay = 0.5 ** (age_h / half_life_hours)

        word_freq: Counter[str] = Counter()
        for i in idxs:
            word_freq.update(toks[i])
        keywords = [w for w, _ in sorted(word_freq.items(), key=lambda kv: kv[1] * idf.get(kv[0], 0), reverse=True)[:6]]
        text = " ".join(a.title.lower() for a in arts)
        boost = 0.5 if any(term and term in text for term in trend_terms) else 0.0

        coverage = sum(outlets.values()) + 0.25 * related
        score = (coverage + math.log1p(len(arts))) * decay * (1 + boost)

        # Representative article: prefer a direct publisher link with a description and image.
        def rank(a: Article) -> tuple:
            direct = not a.source.id.startswith("gn:")
            return (direct, bool(a.description), bool(a.image), weights.get(a.source.id, 1.0), a.published_at or "")

        lead = max(arts, key=rank)
        cats = Counter(a.category for a in arts if a.category != "top")
        category = cats.most_common(1)[0][0] if cats else lead.category
        arts_sorted = sorted(arts, key=lambda a: a.published_at or "", reverse=True)
        stories.append(
            Story(
                id=articles[min(idxs, key=lambda i: articles[i].published_at or "")].id,
                title=lead.title,
                description=lead.description or next((a.description for a in arts if a.description), ""),
                url=lead.url,
                image=lead.image or next((a.image for a in arts if a.image), None),
                category=category,
                score=round(score, 4),
                sources_count=len(outlets),
                articles_count=len(arts),
                first_seen=first.isoformat().replace("+00:00", "Z"),
                latest=latest.isoformat().replace("+00:00", "Z"),
                countries=sorted({a.country for a in arts}),
                sources=sorted({a.source.name for a in arts}),
                keywords=keywords,
                articles=arts_sorted,
            )
        )
    stories.sort(key=lambda s: s.score, reverse=True)
    return stories
