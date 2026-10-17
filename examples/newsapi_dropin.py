"""Existing NewsAPI.org code works against your own server — just change the base URL."""

import requests

BASE = "http://localhost:8000"  # instead of https://newsapi.org

r = requests.get(f"{BASE}/v2/top-headlines", params={"country": "us", "category": "technology", "pageSize": 5})
for a in r.json()["articles"]:
    print(a["publishedAt"], a["source"]["name"], "-", a["title"])

r = requests.get(f"{BASE}/v2/everything", params={"q": "electric vehicles", "pageSize": 5})
for a in r.json()["articles"]:
    print(a["title"], a["url"])
