FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FREENEWS_SNAPSHOT=/data/snapshot.json
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY freenews ./freenews
RUN pip install ".[mcp]" && useradd -r -u 10001 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# One worker: the feed poller and the in-memory index live in this process.
CMD ["sh", "-c", "uvicorn freenews.api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
