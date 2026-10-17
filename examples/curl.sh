#!/usr/bin/env sh
# Free hosted (static, updated every 30 min)
curl https://ethos6.github.io/free-news-api/v1/trending.json
curl https://ethos6.github.io/free-news-api/v1/trending/business.json
curl https://ethos6.github.io/free-news-api/v1/countries/in/trending.json

# Self-hosted (live)
curl "http://localhost:8000/v1/trending?category=technology&limit=10"
curl "http://localhost:8000/v1/headlines?country=gb&category=sports"
curl "http://localhost:8000/v1/search?q=artificial+intelligence"
curl "http://localhost:8000/v1/trends?geo=US"
curl "http://localhost:8000/v1/feed.xml?category=science"

# NewsAPI.org-compatible
curl "http://localhost:8000/v2/top-headlines?country=us&category=business"
curl "http://localhost:8000/v2/everything?q=bitcoin"
