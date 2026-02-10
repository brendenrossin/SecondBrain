"use client";

import { CalendarDays } from "lucide-react";
import type { CalendarEvent } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function MultiDayBanner({ event }: { event: CalendarEvent }) {
  const startDisplay = formatDate(event.date);
  const endDisplay = formatDate(event.end_date);

  return (
    <div className="glass-card overflow-clip">
      <div className="flex items-center gap-3 px-7 py-3 bg-emerald-500/[0.04] border-l-2 border-emerald-500/40">
        <CalendarDays className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        <span className="text-[13px] leading-snug text-text font-medium">
          {event.title}
        </span>
        <span className="ml-auto text-[10px] text-emerald-400 font-medium shrink-0">
          {startDisplay} – {endDisplay}
        </span>
      </div>
    </div>
  );
}
