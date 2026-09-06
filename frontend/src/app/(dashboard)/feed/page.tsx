"use client";

import { useEffect, useState } from "react";
import { Rss } from "lucide-react";
import { getFeed } from "@/lib/api";
import { FeedBlock, FeedLink, headingColor } from "@/components/feed/FeedBlock";
import { cn } from "@/lib/utils";
import type { FeedItem, FeedResponse } from "@/lib/types";

/** Rows past this stay behind a toggle — one source can contribute 17 items. */
const PREVIEW_COUNT = 8;

function EmptyState({ message }: { message: string }): React.JSX.Element {
  return (
    <div className="glass-card p-8 text-center">
      <Rss className="w-10 h-10 text-text-dim mx-auto mb-3" />
      <p className="text-sm font-semibold text-text">Nothing in the feed yet</p>
      <p className="text-[12px] text-text-muted mt-1">{message}</p>
    </div>
  );
}

/**
 * One type's unsummarized leftovers: headline, source and age only.
 *
 * Deliberately no snippets. These are the items the ranker did *not* pick, so
 * they are a scanning surface — 40-odd previews turn the page into a wall and
 * bury the summarized section that actually earned the LLM call.
 */
function RestGroup({ type, items }: { type: string; items: FeedItem[] }): React.JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const heading = type.toUpperCase();
  const shown = expanded ? items : items.slice(0, PREVIEW_COUNT);

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <p
          className={cn(
            "text-[11px] font-semibold uppercase tracking-wide",
            headingColor(heading)
          )}
        >
          {heading}
        </p>
        <span className="text-[10px] text-text-dim">{items.length}</span>
      </div>
      {shown.map((item) => (
        <FeedLink
          key={item.url}
          id={item.id}
          url={item.url}
          title={item.title}
          source={item.source_label}
          publishedAt={item.published_at}
        />
      ))}
      {items.length > PREVIEW_COUNT && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[11px] text-text-dim hover:text-accent transition-colors mt-1.5"
        >
          {expanded ? "Show less" : `Show all ${items.length}`}
        </button>
      )}
    </div>
  );
}

/** Group the leftovers by type, preserving the ranked order they arrived in. */
function groupByType(items: FeedItem[]): [string, FeedItem[]][] {
  const groups = new Map<string, FeedItem[]>();
  for (const item of items) {
    const existing = groups.get(item.type);
    if (existing) existing.push(item);
    else groups.set(item.type, [item]);
  }
  return [...groups];
}

export default function FeedPage(): React.JSX.Element {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getFeed()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Items already shown as a summarized take don't need repeating below.
  const summarizedUrls = new Set(
    (data?.sections ?? []).flatMap((s) => s.items.map((i) => i.url))
  );
  const rest = (data?.items ?? []).filter((i) => !summarizedUrls.has(i.url));

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Rss className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">Feed</h1>
        {data && data.items.length > 0 && (
          <span className="text-[11px] text-text-dim ml-1">
            {data.items.length} item{data.items.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 md:px-6 py-6 space-y-5">
        {loading && <p className="text-[13px] text-text-dim">Loading feed…</p>}

        {!loading && error && <EmptyState message="Could not reach the feed API." />}

        {!loading && !error && data?.items.length === 0 && (
          <EmptyState message="Enable the feed and run the daily sync to populate it." />
        )}

        {!loading && !error && (data?.items.length ?? 0) > 0 && (
          <>
            <FeedBlock data={data ?? undefined} />

            {rest.length > 0 && (
              <div className="glass-card p-5">
                <h2 className="text-sm font-semibold text-text mb-3">
                  More from your sources ({rest.length})
                </h2>
                <div className="space-y-4">
                  {groupByType(rest).map(([type, items]) => (
                    <RestGroup key={type} type={type} items={items} />
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
