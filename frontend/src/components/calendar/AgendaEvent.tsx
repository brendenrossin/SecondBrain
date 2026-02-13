"use client";

import { CalendarDays } from "lucide-react";
import type { CalendarEvent } from "@/lib/types";

function formatTime(time: string): string {
  if (!time) return "";
  const [h, m] = time.split(":");
  const hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 || 12;
  return `${h12}:${m} ${ampm}`;
}

export function AgendaEvent({ event }: { event: CalendarEvent }): React.JSX.Element {
  return (
    <div className="flex items-center gap-3.5 px-7 py-4 hover:bg-card-hover transition-colors border-b border-border/50 last:border-b-0">
      <CalendarDays className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] leading-snug text-text">{event.title}</p>
      </div>
      {event.time && (
        <span className="text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 px-2.5 py-0.5 rounded-lg shrink-0">
          {formatTime(event.time)}
        </span>
      )}
    </div>
  );
}
