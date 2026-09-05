"""Batched daily feed summary — exactly one Anthropic Haiku call, logged to UsageStore.

On any failure, falls back to headlines (generated=False) so the feed still works.
"""

import json
import logging
import time
from typing import Any

import anthropic

from secondbrain.config import Settings
from secondbrain.feed.models import FeedItem, FeedSection, FeedSummary
from secondbrain.stores.usage import UsageStore, calculate_cost

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a terse news editor. Group the provided items into sections by their "
    "type (AI, Sports). For each item write a one-line take (<=20 words). "
    "Respond with ONLY JSON: "
    '{"sections":[{"heading":"AI","items":[{"url":"...","title":"...","take":"..."}]}]}'
)

_PROMPT_SNIPPET_MAX = 200  # prompt-cost trim; fetch.py already caps snippets at 400
_FALLBACK_TAKE_MAX = 120


def build_summary_prompt(items: list[FeedItem]) -> str:
    """One line per item — type, source, title, trimmed snippet, URL."""
    lines = [
        f"- [{it.type}] ({it.source_label}) {it.title} :: {it.snippet[:_PROMPT_SNIPPET_MAX]} <{it.url}>"
        for it in items
    ]
    return "Items:\n" + "\n".join(lines)


def _fallback(items: list[FeedItem]) -> FeedSummary:
    """Headline-only sections, grouped by type — used whenever the LLM path fails."""
    by_type: dict[str, list[dict[str, str]]] = {}
    for it in items:
        by_type.setdefault(it.type, []).append(
            {"url": it.url, "title": it.title, "take": it.snippet[:_FALLBACK_TAKE_MAX]}
        )
    sections = [FeedSection(heading=t.upper(), items=v) for t, v in by_type.items()]
    return FeedSummary(sections=sections, generated=False)


def _section_from_json(raw: Any) -> FeedSection:
    """One section from raw model JSON; missing fields become empty strings.

    Raises on malformed shapes — callers treat that as "fall back to headlines".
    """
    return FeedSection(
        heading=str(raw.get("heading", "")),
        items=[
            {
                "url": str(i.get("url", "")),
                "title": str(i.get("title", "")),
                "take": str(i.get("take", "")),
            }
            for i in raw.get("items", [])
        ],
    )


def parse_summary_response(text: str, items: list[FeedItem]) -> FeedSummary:
    """Parse model JSON; on any problem, fall back to headlines."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
        sections = [_section_from_json(s) for s in data.get("sections", [])]
    except Exception:
        logger.warning("Feed summary parse failed; falling back to headlines", exc_info=True)
        return _fallback(items)
    if not sections:
        return _fallback(items)
    return FeedSummary(sections=sections, generated=True)


def _response_text(resp: anthropic.types.Message) -> str:
    """First text block of the response, or "" — content can be empty."""
    return next((b.text for b in resp.content if b.type == "text"), "")


def summarize_items(
    items: list[FeedItem], settings: Settings, usage_store: UsageStore | None = None
) -> FeedSummary:
    """One batched Haiku call over top items. Falls back to headlines on any failure."""
    if not items:
        return FeedSummary(sections=[], generated=False)
    if not settings.anthropic_api_key:
        logger.info("No anthropic_api_key; feed summary falls back to headlines")
        return _fallback(items)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    model = settings.feed_summary_model
    start = time.perf_counter()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": build_summary_prompt(items)}],
        )
    except Exception:
        logger.warning("Feed summary LLM call failed; using headlines", exc_info=True)
        return _fallback(items)

    if usage_store is not None:
        in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
        usage_store.log_usage(
            provider="anthropic",
            model=model,
            usage_type="feed_summary",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=calculate_cost("anthropic", model, in_tok, out_tok),
            latency_ms=(time.perf_counter() - start) * 1000,
        )
    return parse_summary_response(_response_text(resp), items)
