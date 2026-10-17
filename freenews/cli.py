"""Command line: `freenews serve | trending | headlines | search | trends | build | check | mcp`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import __version__


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="freenews", description="Free, unlimited world trending news API")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)

    t = sub.add_parser("trending", help="print trending stories")
    t.add_argument("-c", "--category")
    t.add_argument("--country")
    t.add_argument("-n", "--limit", type=int, default=15)
    t.add_argument("--json", action="store_true")

    h = sub.add_parser("headlines", help="print latest headlines")
    h.add_argument("-c", "--category")
    h.add_argument("--country")
    h.add_argument("-n", "--limit", type=int, default=20)
    h.add_argument("--json", action="store_true")

    q = sub.add_parser("search", help="search news")
    q.add_argument("query", nargs="+")
    q.add_argument("-n", "--limit", type=int, default=20)
    q.add_argument("--json", action="store_true")

    sub.add_parser("trends", help="Google Trends + Wikipedia most-read")

    b = sub.add_parser("build", help="build the static JSON API (for GitHub Pages)")
    b.add_argument("--out", default="site")
    b.add_argument("--base-url", default="")

    sub.add_parser("check", help="fetch every feed once and print a health table (Markdown)")

    m = sub.add_parser("mcp", help="run as an MCP server")
    m.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8001)

    a = p.parse_args(argv)

    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("freenews.api:app", host=a.host, port=a.port)
        return
    if a.cmd == "mcp":
        from .mcp_server import run

        run(a.transport, a.host, a.port)
        return
    if a.cmd == "build":
        from .static_build import build

        print(json.dumps(asyncio.run(build(a.out, a.base_url)), indent=2))
        return

    from .core import NewsHub

    async def go() -> int:
        async with NewsHub() as hub:
            if a.cmd == "search":
                arts = await hub.search(" ".join(a.query), limit=a.limit)
                _print_articles(arts, a.json)
                return 0
            summary = await hub.refresh()
            print(f"# {summary}", file=sys.stderr)
            if a.cmd == "trending":
                stories = hub.trending(category=a.category, country=a.country, limit=a.limit)
                if a.json:
                    print(json.dumps([s.model_dump() for s in stories], indent=2))
                else:
                    for i, st in enumerate(stories, 1):
                        print(
                            f"{i:>2}. [{st.sources_count} outlets · {st.category}] {st.title}\n    {st.url}\n    {', '.join(st.sources[:6])}"
                        )
            elif a.cmd == "headlines":
                _total, arts = hub.headlines(category=a.category, country=a.country, limit=a.limit)
                _print_articles(arts, a.json)
            elif a.cmd == "trends":
                print(json.dumps(hub.trend_items(), indent=2, ensure_ascii=False))
            elif a.cmd == "check":
                rows = sorted(hub.feed_status(), key=lambda s: (bool(s.ok), s.id))
                print("| feed | status | articles | ms | error |\n|---|---|---|---|---|")
                for st in rows:
                    mark = "✅" if st.ok else "❌"
                    print(f"| {st.id} | {mark} | {st.articles} | {st.elapsed_ms} | {st.error or ''} |")
                ok = sum(1 for s in rows if s.ok)
                g = {k: len(v) for k, v in hub.trends.items()}
                print(
                    f"\n**{ok}/{len(rows)} feeds OK** · {summary['total_articles']} articles · "
                    f"Google Trends: {g} · Wikipedia most-read: {len(hub.wikipedia)}"
                )
                top = hub.trending(limit=10)
                print("\n**Top trending now:**\n")
                for i, st in enumerate(top, 1):
                    print(f"{i}. {st.title} — {st.sources_count} outlets")
                return 0 if ok >= len(rows) * 0.6 else 1
        return 0

    sys.exit(asyncio.run(go()))


def _print_articles(arts, as_json: bool) -> None:
    if as_json:
        print(json.dumps([x.model_dump() for x in arts], indent=2, ensure_ascii=False))
        return
    for x in arts:
        print(f"- {x.title}  ({x.source.name}, {x.published_at})\n  {x.url}")


if __name__ == "__main__":
    main()
