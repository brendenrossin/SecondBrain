"use client";

import type { TaskResponse } from "@/lib/types";
import { cn, toDateStr } from "@/lib/utils";
import { AgendaTask } from "./AgendaTask";

interface DaySectionProps {
  date: Date;
  tasks: TaskResponse[];
}

export function DaySection({ date, tasks }: DaySectionProps) {
  const isToday = toDateStr(date) === toDateStr(new Date());
  const dayName = date.toLocaleDateString("en-US", { weekday: "long" });
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  return (
    <div
      className={cn(
        "overflow-hidden transition-all duration-200",
        isToday ? "glass-card glass-card-accent" : "glass-card"
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 px-5 py-3 border-b",
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
          {tasks.length} task{tasks.length !== 1 ? "s" : ""}
        </span>
      </div>
      {tasks.map((task, i) => (
        <AgendaTask key={i} task={task} />
      ))}
    </div>
  );
}
