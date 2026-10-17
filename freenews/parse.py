"""Turn RSS / Atom / RDF feeds into normalized Article objects."""

from __future__ import annotations

import calendar
import hashlib
import html
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser

from .models import Article, SourceRef
from .sources import Source

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
_LI = re.compile(r"<li\b", re.I)
TRACKING = {
    "fbclid",
    "gclid",
    "cmpid",
    "ito",
    "ns_mchannel",
    "ns_source",
    "ns_campaign",
    "ns_linkname",
    "ns_fee",
    "at_medium",
    "at_campaign",
    "smid",
    "partner",
    "taid",
    "mod",
    "ref",
}


def clean_text(value: str | None, limit: int = 600) -> str:
    if not value:
        return ""
    text = _WS.sub(" ", html.unescape(_TAG.sub(" ", value))).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING
        ]
    )
    return urlunparse((p.scheme or "https", p.netloc.lower(), p.path, "", query, ""))


def article_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:16]


def domain(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def to_iso(struct) -> str | None:
    if not struct:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, ValueError, TypeError):
        return None


def _image(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            url = m.get("url")
            if url and (m.get("medium") in (None, "image") or key == "media_thumbnail"):
                return url
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    for link in entry.get("links") or []:
        if str(link.get("type", "")).startswith("image") and link.get("href"):
            return link["href"]
    blob = entry.get("summary", "") + "".join(c.get("value", "") for c in entry.get("content") or [])
    m = _IMG.search(blob)
    return html.unescape(m.group(1)) if m else None


def parse_feed(content: bytes | str, source: Source, now: datetime | None = None) -> list[Article]:
    parsed = feedparser.parse(content)
    now_iso = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out: list[Article] = []
    for entry in parsed.entries:
        url = entry.get("link") or ""
        title = clean_text(entry.get("title"), 300)
        if not url.startswith(("http://", "https://")) or not title:
            continue
        published = to_iso(entry.get("published_parsed") or entry.get("updated_parsed"))
        if published and published > now_iso:  # some feeds publish future-dated items
            published = now_iso
        if source.kind == "google_news":
            src = entry.get("source") or {}
            pub_name = src.get("title") or ""
            pub_url = src.get("href")
            if pub_name and title.endswith(" - " + pub_name):
                title = title[: -len(pub_name) - 3]
            related = max(0, len(_LI.findall(entry.get("summary", ""))) - 1)
            ref = SourceRef(id=f"gn:{domain(pub_url) or pub_name.lower()}", name=pub_name or source.name, domain=domain(pub_url))
            description = ""
        elif source.kind == "bing_news":
            target = dict(parse_qsl(urlparse(url).query)).get("url")
            if target and target.startswith("http"):
                url = target
            pub_name = clean_text(entry.get("news_source"), 120) or source.name
            related = 0
            ref = SourceRef(id=f"bn:{domain(url)}", name=pub_name, domain=domain(url))
            description = clean_text(entry.get("summary") or "")
        else:
            related = 0
            ref = SourceRef(id=source.id, name=source.name, domain=domain(url))
            description = clean_text(entry.get("summary") or "")
        out.append(
            Article(
                id=article_id(url),
                title=title,
                url=url,
                description=description,
                source=ref,
                category=source.category,
                country=source.country,
                language=source.language,
                published_at=published,
                image=_image(entry),
                author=clean_text(entry.get("author"), 120) or None,
                related_count=related,
            )
        )
    return out
