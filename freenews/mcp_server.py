"""MCP server: world trending news for Claude Desktop, Cursor, Windsurf and other agents.

freenews mcp                                  # stdio
freenews mcp --transport streamable-http      # http://localhost:8001/mcp
"""

from __future__ import annotations

import time
from typing import Any

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]

from .core import NewsHub

_hub: NewsHub | None = None
_last = 0.0


async def _get() -> NewsHub:
    """Lazily refresh: at most once per configured interval."""
    global _hub, _last
    if _hub is None:
        _hub = NewsHub()
    if time.monotonic() - _last > _hub.settings.refresh_minutes * 60 or not _hub.articles:
        await _hub.refresh()
        _last = time.monotonic()
    return _hub


def build_server() -> Any:
    server = MCPServer("freenews", instructions="World news. Start with trending_news; use search_news for a topic.")

    @server.tool()
    async def trending_news(category: str = "top", country: str | None = None, limit: int = 10) -> str:
        """Top trending stories right now, ranked by how many outlets cover them.

        Args:
            category: top, world, business, technology, science, health, sports or entertainment
            country: optional ISO code, e.g. us, gb, in
            limit: 1-30
        """
        hub = await _get()
        stories = hub.trending(category=category, country=country, limit=max(1, min(limit, 30)))
        return (
            "\n\n".join(
                f"{i}. {s.title}\n   {s.url}\n   {s.sources_count} outlets ({', '.join(s.sources[:5])}) · {s.latest}\n   {s.description[:300]}"
                for i, s in enumerate(stories, 1)
            )
            or "No stories yet."
        )

    @server.tool()
    async def latest_headlines(category: str = "top", country: str | None = None, limit: int = 15) -> str:
        """Newest headlines, optionally filtered by category and country."""
        hub = await _get()
        _total, arts = hub.headlines(category=category, country=country, limit=max(1, min(limit, 50)))
        return "\n".join(f"- {a.title} ({a.source.name}, {a.published_at})\n  {a.url}" for a in arts) or "No headlines."

    @server.tool()
    async def search_news(query: str, limit: int = 15) -> str:
        """Search recent news on any topic."""
        hub = await _get()
        arts = await hub.search(query, limit=max(1, min(limit, 50)))
        return "\n".join(f"- {a.title} ({a.source.name}, {a.published_at})\n  {a.url}" for a in arts) or "No results."

    @server.tool()
    async def trending_searches(geo: str = "US") -> str:
        """What people are searching on Google and reading on Wikipedia right now."""
        hub = await _get()
        data = hub.trend_items(geo)
        g = data["google_trends"].get(geo.upper(), [])
        lines = ["Google Trends:"] + [f"- {t['title']} ({t.get('traffic') or ''})" for t in g[:15]]
        lines += ["", "Wikipedia most read:"] + [f"- {t['title']} ({t.get('traffic')})" for t in data["wikipedia_most_read"][:10]]
        return "\n".join(lines)

    return server


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8001) -> None:
    server = build_server()
    if transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=host, port=port)
