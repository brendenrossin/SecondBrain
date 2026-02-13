"use client";

import { useMemo } from "react";
import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { addDays, toDateStr } from "@/lib/utils";
import { DayColumn } from "./DayColumn";

interface WeekGridProps {
  weekStart: Date;
  tasks: TaskResponse[];
  events: CalendarEvent[];
  showWeekend: boolean;
  onTaskUpdate?: () => void;
  onTaskSelect?: (task: TaskResponse) => void;
}

export function WeekGrid({
  weekStart,
  tasks,
  events,
  showWeekend,
  onTaskUpdate,
  onTaskSelect,
}: WeekGridProps): React.JSX.Element {
  const todayStr = toDateStr(new Date());
  const columnCount = showWeekend ? 7 : 5;

  const columns = useMemo(() => {
    // Group tasks by due date
    const tasksByDay = new Map<string, TaskResponse[]>();
    const eventsByDay = new Map<string, CalendarEvent[]>();

    for (let i = 0; i < columnCount; i++) {
      const ds = toDateStr(addDays(weekStart, i));
      tasksByDay.set(ds, []);
      eventsByDay.set(ds, []);
    }

    for (const task of tasks) {
      if (!task.due_date) continue;
      const bucket = tasksByDay.get(task.due_date);
      if (bucket) bucket.push(task);
    }

    // Only include single-day events (multi-day handled by banner)
    for (const event of events) {
      if (event.end_date) continue;
      const bucket = eventsByDay.get(event.date);
      if (bucket) bucket.push(event);
    }

    return Array.from({ length: columnCount }, (_, i) => {
      const date = addDays(weekStart, i);
      const ds = toDateStr(date);
      return {
        date,
        dateStr: ds,
        tasks: tasksByDay.get(ds) || [],
        events: eventsByDay.get(ds) || [],
      };
    });
  }, [weekStart, tasks, events, columnCount]);

  return (
    <div className="rounded-2xl border border-border bg-surface-1 overflow-hidden">
      <div
        className="flex flex-row min-h-[300px]"
        style={{ maxHeight: "calc(100vh - 280px)" }}
      >
        {columns.map((col, i) => (
          <DayColumn
            key={col.dateStr}
            date={col.date}
            events={col.events}
            tasks={col.tasks}
            isToday={col.dateStr === todayStr}
            isLast={i === columns.length - 1}
            onTaskUpdate={onTaskUpdate}
            onTaskSelect={onTaskSelect}
          />
        ))}
      </div>
    </div>
  );
}
