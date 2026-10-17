"""Read the free hosted API (no server) or your own instance."""

import requests

BASE = "https://ethos6.github.io/free-news-api"  # or "http://localhost:8000" for a self-hosted server

data = requests.get(f"{BASE}/v1/trending.json", timeout=20).json()
print("updated:", data["updated_at"])
for i, story in enumerate(data["stories"][:10], 1):
    print(f"{i}. {story['title']}  [{story['sources_count']} outlets]")
    print(f"   {story['url']}")
