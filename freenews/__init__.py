"""FreeNews API — free, unlimited, self-hosted API for the world's top trending news."""

__version__ = "1.0.0"

from .config import Settings  # noqa: E402
from .core import NewsHub  # noqa: E402
from .models import Article, Story, TrendItem  # noqa: E402

__all__ = ["Article", "NewsHub", "Settings", "Story", "TrendItem", "__version__"]
