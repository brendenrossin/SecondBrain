"""Feed domain models (dataclasses — transient, not vault content)."""

from dataclasses import dataclass, field


@dataclass
class FeedSource:
    url: str
    label: str
    type: str  # "ai" | "sports" | "general"
    trust: float = 0.5


@dataclass
class FeedConfig:
    sources: list[FeedSource]
    interests: dict[str, float]  # keyword -> weight


@dataclass
class FeedItem:
    url: str
    source_label: str
    type: str
    title: str
    snippet: str
    published_at: str | None = None  # ISO 8601 or None
    trust: float = 0.5
    score: float = 0.0
    summary: str | None = None


@dataclass
class FeedSection:
    heading: str  # "AI" | "Sports"
    items: list[dict[str, str]] = field(default_factory=list)  # {title, url, take}


@dataclass
class FeedSummary:
    sections: list[FeedSection]
    generated: bool  # False when the LLM call failed and we fell back to headlines
