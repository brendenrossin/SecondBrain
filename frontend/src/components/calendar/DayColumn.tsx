"use client";

import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CompactEvent } from "./CompactEvent";
import { CompactTask } from "./CompactTask";

interface DayColumnProps {
  date: Date;
  events: CalendarEvent[];
  tasks: TaskResponse[];
  isToday: boolean;
  isLast: boolean;
  onTaskUpdate?: () => void;
  onTaskSelect?: (task: TaskResponse) => void;
}

export function DayColumn({
  date,
  events,
  tasks,
  isToday,
  isLast,
  onTaskUpdate,
  onTaskSelect,
}: DayColumnProps): React.JSX.Element {
  const dayAbbr = date.toLocaleDateString("en-US", { weekday: "short" });
  const dateNum = date.getDate();

  return (
    <div
      className={cn(
        "flex-1 min-w-0 flex flex-col",
        !isLast && "border-r border-border"
      )}
    >
      {/* Header */}
      <div className="px-2 py-3 border-b border-border text-center">
        <p className="text-[10px] text-text-dim uppercase tracking-wide font-medium">
          {dayAbbr}
        </p>
        <p
          className={cn(
            "text-lg font-semibold leading-tight",
            isToday ? "text-accent" : "text-text"
          )}
        >
          {dateNum}
        </p>
        {isToday && (
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-accent mt-0.5" />
        )}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-1 space-y-0.5">
        {events.map((event) => (
          <CompactEvent key={`e-${event.title}-${event.time}`} event={event} />
        ))}
        {tasks.map((task) => (
          <CompactTask
            key={`t-${task.text}`}
            task={task}
            onUpdate={onTaskUpdate}
            onSelect={onTaskSelect}
          />
        ))}
        {events.length === 0 && tasks.length === 0 && (
          <div className="py-4" />
        )}
      </div>
    </div>
  );
}
