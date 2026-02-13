"use client";

import { CalendarDays } from "lucide-react";
import type { CalendarEvent } from "@/lib/types";

function formatCompactTime(time: string): string {
  if (!time) return "";
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "p" : "a";
  const hour12 = h % 12 || 12;
  return `${hour12}:${m.toString().padStart(2, "0")}${suffix}`;
}

export function CompactEvent({ event }: { event: CalendarEvent }): React.JSX.Element {
  return (
    <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.03] transition-colors">
      <CalendarDays className="w-3 h-3 text-emerald-400 shrink-0" />
      <span className="text-xs text-text truncate flex-1 min-w-0">{event.title}</span>
      {event.time && (
        <span className="text-[10px] text-emerald-400 font-medium shrink-0">
          {formatCompactTime(event.time)}
        </span>
      )}
    </div>
  );
}
