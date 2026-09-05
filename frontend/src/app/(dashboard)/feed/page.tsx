"use client";

import { useEffect, useState } from "react";
import { Rss } from "lucide-react";
import { cn } from "@/lib/utils";
import { getFeed } from "@/lib/api";
import { FeedBlock, FeedLink } from "@/components/feed/FeedBlock";
import type { FeedResponse } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = { ai: "AI", sports: "Sports" };

function EmptyState({ message }: { message: string }): React.JSX.Element {
  return (
    <div className="glass-card p-8 text-center">
      <Rss className="w-10 h-10 text-text-dim mx-auto mb-3" />
      <p className="text-sm font-semibold text-text">Nothing in the feed yet</p>
      <p className="text-[12px] text-text-muted mt-1">{message}</p>
    </div>
  );
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

        {!loading && error && (
          <EmptyState message="Could not reach the feed API." />
        )}

        {!loading && !error && data?.items.length === 0 && (
          <EmptyState message="Enable the feed and run the daily sync to populate it." />
        )}

        {!loading && !error && (data?.items.length ?? 0) > 0 && (
          <>
            <FeedBlock />

            {rest.length > 0 && (
              <div className="glass-card p-5">
                <h2 className="text-sm font-semibold text-text mb-3">
                  Everything else ({rest.length})
                </h2>
                <div className="divide-y divide-border/40">
                  {rest.map((item) => (
                    <FeedLink
                      key={item.url}
                      id={item.id}
                      url={item.url}
                      title={item.title}
                      take={item.snippet || null}
                      source={cn(
                        item.source_label,
                        TYPE_LABEL[item.type] ? ` · ${TYPE_LABEL[item.type]}` : ""
                      )}
                    />
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
