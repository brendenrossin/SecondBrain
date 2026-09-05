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
    "You are a terse news editor. Group the numbered items into sections by their "
    "type (AI, Sports). For each item write a one-line take (<=20 words). "
    "Refer to each item ONLY by its number `i` — never invent or copy a URL. "
    "Respond with ONLY JSON: "
    '{"sections":[{"heading":"AI","items":[{"i":1,"take":"..."}]}]}'
)

_PROMPT_SNIPPET_MAX = 200  # prompt-cost trim; fetch.py already caps snippets at 400


def build_summary_prompt(items: list[FeedItem]) -> str:
    """One numbered line per item — index, type, source, title, trimmed snippet.

    URLs are deliberately withheld. Asking the model to echo them back made it
    substitute links found inside the snippets (observed live: 2 of 10 items
    came back with a URL from the article body), so those takes silently failed
    to reattach. Indexes cannot be mistranscribed, halve the output tokens, and
    keep model-controlled text out of anything that becomes an href.
    """
    lines = [
        f"{n}. [{it.type}] ({it.source_label}) {it.title} :: {it.snippet[:_PROMPT_SNIPPET_MAX]}"
        for n, it in enumerate(items, start=1)
    ]
    return "Items:\n" + "\n".join(lines)


def _fallback(items: list[FeedItem]) -> FeedSummary:
    """Headline-only sections, grouped by type — used whenever the LLM path fails.

    The `take` is deliberately empty rather than a truncated snippet: the pipeline
    persists takes into `summary`, and a snippet stored there would be
    indistinguishable from a real LLM take, making `generated` report True for a
    run that never reached the model. The UI already falls back to the snippet.
    """
    by_type: dict[str, list[dict[str, str]]] = {}
    for it in items:
        by_type.setdefault(it.type, []).append({"url": it.url, "title": it.title, "take": ""})
    sections = [FeedSection(heading=t.upper(), items=v) for t, v in by_type.items()]
    return FeedSummary(sections=sections, generated=False)


def _section_from_json(raw: Any, items: list[FeedItem]) -> FeedSection:
    """One section from raw model JSON, resolving 1-based indexes against `items`.

    url and title always come from our own data, never from the model. An index
    that is out of range or repeated is dropped rather than guessed at.

    Raises on malformed shapes — callers treat that as "fall back to headlines".
    """
    resolved: list[dict[str, str]] = []
    seen: set[int] = set()
    for entry in raw.get("items", []):
        try:
            idx = int(entry["i"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= idx < len(items)) or idx in seen:
            continue
        seen.add(idx)
        item = items[idx]
        resolved.append({"url": item.url, "title": item.title, "take": str(entry.get("take", ""))})
    return FeedSection(heading=str(raw.get("heading", "")), items=resolved)


def parse_summary_response(text: str, items: list[FeedItem]) -> FeedSummary:
    """Parse model JSON; on any problem, fall back to headlines."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
        sections = [_section_from_json(s, items) for s in data.get("sections", [])]
    except Exception:
        logger.warning("Feed summary parse failed; falling back to headlines", exc_info=True)
        return _fallback(items)
    if not any(section.items for section in sections):
        # Every index was unusable — no better than not having called at all.
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
            max_tokens=2048,
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
    if getattr(resp, "stop_reason", None) == "max_tokens":
        # Distinguish a truncated (paid, wasted) response from malformed JSON.
        logger.warning("Feed summary hit max_tokens; response truncated")
    return parse_summary_response(_response_text(resp), items)
