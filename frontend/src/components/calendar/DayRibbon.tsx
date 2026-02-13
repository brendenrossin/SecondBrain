"use client";

import { useMemo } from "react";
import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { addDays, toDateStr } from "@/lib/utils";
import { DayButton } from "./DayButton";

interface DayRibbonProps {
  weekStart: Date;
  tasks: TaskResponse[];
  events: CalendarEvent[];
  selectedDate: Date;
  onSelectDate: (date: Date) => void;
}

export function DayRibbon({
  weekStart,
  tasks,
  events,
  selectedDate,
  onSelectDate,
}: DayRibbonProps): React.JSX.Element {
  const todayStr = toDateStr(new Date());
  const selectedStr = toDateStr(selectedDate);

  const days = useMemo(() => {
    return Array.from({ length: 7 }, (_, i) => {
      const date = addDays(weekStart, i);
      const ds = toDateStr(date);

      // Count events for this day (including multi-day events that span it)
      const dayEvents = events.filter((e) => {
        const start = e.date;
        const end = e.end_date || e.date;
        return ds >= start && ds <= end;
      });

      // Count tasks due this day
      const dayTasks = tasks.filter((t) => t.due_date === ds);
      const hasOverdue = dayTasks.some((t) => t.due_date < todayStr);
      const hasDueSoon = ds === todayStr && dayTasks.length > 0;

      return {
        date,
        dateStr: ds,
        eventCount: dayEvents.length,
        taskCount: dayTasks.length,
        hasOverdue,
        hasDueSoon,
      };
    });
  }, [weekStart, tasks, events, todayStr]);

  return (
    <div className="flex flex-row bg-surface-1 border-b border-border rounded-t-2xl overflow-hidden">
      {days.map((day) => (
        <DayButton
          key={day.dateStr}
          date={day.date}
          eventCount={day.eventCount}
          taskCount={day.taskCount}
          hasOverdue={day.hasOverdue}
          hasDueSoon={day.hasDueSoon}
          isSelected={day.dateStr === selectedStr}
          isToday={day.dateStr === todayStr}
          onClick={() => onSelectDate(day.date)}
        />
      ))}
    </div>
  );
}
