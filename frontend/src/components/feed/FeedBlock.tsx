"use client";

import { useEffect, useState } from "react";
import { Rss, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { getFeed, recordFeedClick } from "@/lib/api";
import type { FeedResponse, FeedItem } from "@/lib/types";

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
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => id !== undefined && recordFeedClick(id)}
      className={cn(
        "group flex items-start gap-2.5 py-2 -mx-2 px-2 rounded-lg transition-colors hover:bg-white/[0.04]",
        className
      )}
    >
      <ExternalLink className="w-3.5 h-3.5 text-text-dim shrink-0 mt-0.5 group-hover:text-accent transition-colors" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-text font-medium break-words leading-snug">{title}</p>
        {take && <p className="text-[12px] text-text-muted mt-0.5 break-words">{take}</p>}
        {source && <p className="text-[10px] text-text-dim mt-1">{source}</p>}
      </div>
    </a>
  );
}

/**
 * The feed's Today-surface block: the day's summarized sections only.
 * Renders nothing when the feature is off or nothing has been summarized,
 * so the briefing stays clean.
 */
export function FeedBlock(): React.JSX.Element | null {
  const [data, setData] = useState<FeedResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFeed()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
