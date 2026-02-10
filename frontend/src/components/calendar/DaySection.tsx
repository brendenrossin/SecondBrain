"use client";

import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { cn, toDateStr } from "@/lib/utils";
import { AgendaTask } from "./AgendaTask";
import { AgendaEvent } from "./AgendaEvent";

interface DaySectionProps {
  date: Date;
  tasks: TaskResponse[];
  events?: CalendarEvent[];
}

export function DaySection({ date, tasks, events = [] }: DaySectionProps) {
  const isToday = toDateStr(date) === toDateStr(new Date());
  const dayName = date.toLocaleDateString("en-US", { weekday: "long" });
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  const countParts: string[] = [];
  if (events.length > 0) {
    countParts.push(`${events.length} event${events.length !== 1 ? "s" : ""}`);
  }
  countParts.push(`${tasks.length} task${tasks.length !== 1 ? "s" : ""}`);
  const countLabel = countParts.join(", ");

  return (
    <div
      className={cn(
        "overflow-clip transition-all duration-200",
        isToday ? "glass-card glass-card-accent" : "glass-card"
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2.5 px-7 py-4 border-b",
          isToday ? "border-accent/15" : "border-border"
        )}
      >
        <span
          className={cn(
            "text-xs font-bold tracking-tight",
            isToday ? "text-accent drop-shadow-[0_0_8px_rgba(79,142,247,0.3)]" : "text-text-muted"
          )}
        >
          {dayName}, {dateStr}
        </span>
        {isToday && (
          <span className="text-[10px] font-semibold bg-accent/15 text-accent px-2.5 py-0.5 rounded-lg shadow-[0_0_8px_rgba(79,142,247,0.1)]">
            Today
          </span>
        )}
        <span className="ml-auto text-[10px] text-text-dim font-medium">
          {countLabel}
        </span>
      </div>
      {events.map((event, i) => (
        <AgendaEvent key={`event-${i}`} event={event} />
      ))}
      {tasks.map((task, i) => (
        <AgendaTask key={`task-${i}`} task={task} />
      ))}
    </div>
  );
}
