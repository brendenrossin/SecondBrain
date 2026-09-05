"use client";

import { useEffect, useState } from "react";
import { Rss, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { getFeed, recordFeedClick } from "@/lib/api";
import type { FeedResponse, FeedItem } from "@/lib/types";

/**
 * Feed content is attacker-influenced — anyone who can land an entry in a
 * subscribed feed controls the link, and React does not sanitize `href`.
 * The backend already drops non-http(s) schemes at ingestion; this is the
 * second layer, so a stale row can never render a `javascript:` link.
 */
function safeHref(url: string): string | undefined {
  try {
    // No base URL on purpose: feed links are always absolute, and omitting it
    // keeps this safe to call during SSR where `window` does not exist.
    const { protocol } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? url : undefined;
  } catch {
    return undefined;
  }
}

/** Per-type accent so AI and Sports read apart at a glance. */
const HEADING_COLOR: Record<string, string> = {
  AI: "text-accent",
  SPORTS: "text-success",
};

function headingColor(heading: string): string {
  return HEADING_COLOR[heading] ?? "text-purple";
}

export function FeedLink({
  id,
  url,
  title,
  take,
  source,
  className,
}: {
  id?: number;
  url: string;
  title: string;
  take?: string | null;
  source?: string;
  className?: string;
}): React.JSX.Element {
  const href = safeHref(url);

  // An unsafe or unparseable URL still shows its title — it just isn't clickable.
  const Wrapper = href ? "a" : "div";

  return (
    <Wrapper
      {...(href
        ? {
            href,
            target: "_blank",
            rel: "noopener noreferrer",
            onClick: () => id !== undefined && recordFeedClick(id),
          }
        : {})}
      className={cn(
        "group flex items-start gap-2.5 py-2 -mx-2 px-2 rounded-lg transition-colors",
        href ? "hover:bg-white/[0.04]" : "opacity-60",
        className
      )}
    >
      <ExternalLink className="w-3.5 h-3.5 text-text-dim shrink-0 mt-0.5 group-hover:text-accent transition-colors" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-text font-medium break-words leading-snug">{title}</p>
        {take && <p className="text-[12px] text-text-muted mt-0.5 break-words">{take}</p>}
        {source && <p className="text-[10px] text-text-dim mt-1">{source}</p>}
      </div>
    </Wrapper>
  );
}

/**
 * The feed's Today-surface block: the day's summarized sections only.
 * Renders nothing when the feature is off or nothing has been summarized,
 * so the briefing stays clean.
 */
export function FeedBlock({
  data: provided,
}: {
  /** Pass already-fetched data to avoid a second request. When omitted (the
   *  briefing surface), the block fetches for itself. */
  data?: FeedResponse;
} = {}): React.JSX.Element | null {
  const [fetched, setFetched] = useState<FeedResponse | null>(null);

  useEffect(() => {
    if (provided) return;
    let cancelled = false;
    getFeed()
      .then((res) => {
        if (!cancelled) setFetched(res);
      })
      .catch(() => {
        if (!cancelled) setFetched(null);
      });
    return () => {
      cancelled = true;
    };
  }, [provided]);

  const data = provided ?? fetched;
  if (!data || data.sections.length === 0) return null;

  const byUrl = new Map<string, FeedItem>(data.items.map((i) => [i.url, i]));

  return (
    <div className="glass-card p-5" style={{ borderColor: "rgba(251, 191, 36, 0.15)" }}>
      <div className="flex items-center gap-2 mb-3">
        <Rss className="w-4.5 h-4.5 text-warning" />
        <h2 className="text-sm font-semibold text-text">Feed</h2>
        {!data.generated && (
          <span className="text-[10px] text-text-dim">headlines only</span>
        )}
      </div>
      <div className="space-y-4">
        {data.sections.map((section) => (
          <div key={section.heading}>
            <p
              className={cn(
                "text-[11px] font-semibold uppercase tracking-wide mb-1",
                headingColor(section.heading)
              )}
            >
              {section.heading}
            </p>
            {section.items.map((item) => (
              <FeedLink
                key={item.url}
                id={byUrl.get(item.url)?.id}
                url={item.url}
                title={item.title}
                take={item.take}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
