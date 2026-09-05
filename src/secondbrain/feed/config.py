"""Feed source/interest config — vault-as-truth with built-in seed defaults.

Reads a vault note (default ``_config/feed.md``) whose frontmatter lists sources
and interests. Missing or malformed config falls back to seed defaults; never crashes.
Seed source URLs were verified live on 2026-09-05; a source that later dies is
logged and skipped, never fatal.
"""

import logging
from pathlib import Path

import frontmatter

from secondbrain.feed.models import FeedConfig, FeedSource

logger = logging.getLogger(__name__)

SEED_DEFAULTS = FeedConfig(
    sources=[
        # AI — blogs + newsletters (free RSS, high signal). All verified live 2026-09-05;
        # deeplearning.ai and anthropic.com no longer serve RSS at all.
        FeedSource("https://simonwillison.net/atom/everything/", "Simon Willison", "ai", 0.9),
        FeedSource("https://www.latent.space/feed", "Latent Space", "ai", 0.8),
        FeedSource("https://importai.substack.com/feed", "Import AI", "ai", 0.8),
        FeedSource(
            "https://www.technologyreview.com/topic/artificial-intelligence/feed",
            "MIT Tech Review AI",
            "ai",
            0.7,
        ),
        # Aggregated, so noisier — the points filter is what makes it worth a slot.
        FeedSource("https://hnrss.org/newest?q=AI&points=100", "Hacker News AI", "ai", 0.6),
        # Sports — team-specific where it exists, league-level fallback. Verified live 2026-09-05.
        FeedSource("https://www.mlb.com/padres/feeds/news/rss.xml", "Padres", "sports", 0.8),
        FeedSource("https://mgoblog.com/rss.xml", "Michigan FB (MGoBlog)", "sports", 0.7),
        FeedSource("https://www.espn.com/espn/rss/nfl/news", "NFL (ESPN)", "sports", 0.6),
    ],
    interests={
        # AI
        "agents": 2.0,
        "anthropic": 2.0,
        "claude": 1.8,
        "llm": 1.5,
        "rag": 1.5,
        "openai": 1.2,
        "model": 1.0,
        "eval": 1.2,
        "prompt": 1.0,
        # Sports
        "padres": 2.0,
        "michigan": 2.0,
        "wolverines": 1.8,
        "nfl": 1.2,
        "playoff": 1.2,
    },
)


def parse_feed_config(text: str) -> FeedConfig:
    """Parse frontmatter text into a FeedConfig, falling back to defaults on any problem."""
    try:
        post = frontmatter.loads(text)
        raw_sources = post.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            return SEED_DEFAULTS
        sources = [
            FeedSource(
                url=str(s["url"]),
                label=str(s.get("label", s["url"])),
                type=str(s.get("type", "general")),
                trust=float(s.get("trust", 0.5)),
            )
            for s in raw_sources
            if isinstance(s, dict) and s.get("url")
        ]
        if not sources:
            return SEED_DEFAULTS
        raw_interests = post.get("interests")
        interests = (
            {str(k): float(v) for k, v in raw_interests.items()}
            if isinstance(raw_interests, dict)
            else {}
        )
        return FeedConfig(sources=sources, interests=interests)
    except Exception:
        logger.warning("Feed config parse failed; using seed defaults", exc_info=True)
        return SEED_DEFAULTS


def load_feed_config(vault_path: Path, rel_path: str) -> FeedConfig:
    """Load feed config from a vault note; seed defaults if absent/unreadable."""
    config_file = vault_path / rel_path
    if not config_file.exists():
        logger.info("No feed config at %s; using seed defaults", config_file)
        return SEED_DEFAULTS
    try:
        return parse_feed_config(config_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read feed config %s; using defaults", config_file, exc_info=True)
        return SEED_DEFAULTS
