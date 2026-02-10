"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { getTasks, getEvents } from "@/lib/api";
import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { startOfWeek, addDays, toDateStr, formatDate } from "@/lib/utils";
import { WeekNav } from "./WeekNav";
import { OverdueSection } from "./OverdueSection";
import { DaySection } from "./DaySection";
import { AgendaTask } from "./AgendaTask";
import { MultiDayBanner } from "./MultiDayBanner";

type AgendaSection =
  | { type: "day"; date: string; tasks: TaskResponse[]; events: CalendarEvent[] }
  | { type: "empty-range"; startDate: string; endDate: string };

export function WeeklyAgenda() {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);

  const weekStart = useMemo(
    () => addDays(startOfWeek(new Date()), weekOffset * 7),
    [weekOffset]
  );
  const weekEnd = addDays(weekStart, 6);
  const weekStartStr = toDateStr(weekStart);
  const weekEndStr = toDateStr(weekEnd);
  const todayStr = toDateStr(new Date());

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [taskData, eventData] = await Promise.all([
        getTasks({ completed: false }),
        getEvents(weekStartStr, weekEndStr),
      ]);
      setTasks(taskData);
      setEvents(eventData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [weekStartStr, weekEndStr]);

  useEffect(() => {
    load();
  }, [load]);

  const { overdue, daySections, noDueDate, multiDayEvents } = useMemo(() => {
    const overdue: TaskResponse[] = [];
    const noDueDate: TaskResponse[] = [];
    const byDay = new Map<string, TaskResponse[]>();
    const eventsByDay = new Map<string, CalendarEvent[]>();

    for (let i = 0; i < 7; i++) {
      const ds = toDateStr(addDays(weekStart, i));
      byDay.set(ds, []);
      eventsByDay.set(ds, []);
    }

    for (const task of tasks) {
      if (!task.due_date) {
        noDueDate.push(task);
        continue;
      }
      if (task.due_date < todayStr) {
        overdue.push(task);
      }
      const existing = byDay.get(task.due_date);
      if (existing) {
        existing.push(task);
      }
    }

    // Separate multi-day and single-day events
    const multiDayEvents: CalendarEvent[] = [];
    for (const event of events) {
      if (event.end_date) {
        multiDayEvents.push(event);
      } else {
        const dayEvents = eventsByDay.get(event.date);
        if (dayEvents) {
          dayEvents.push(event);
        }
      }
    }

    // Build sections, combining consecutive empty days
    const sections: AgendaSection[] = [];
    const dayKeys = Array.from(byDay.keys());
    let emptyStart: string | null = null;
    let emptyEnd: string | null = null;

    for (const dateStr of dayKeys) {
      const dayTasks = byDay.get(dateStr) || [];
      const dayEvents = eventsByDay.get(dateStr) || [];
      const hasContent = dayTasks.length > 0 || dayEvents.length > 0;

      if (!hasContent) {
        if (!emptyStart) emptyStart = dateStr;
        emptyEnd = dateStr;
      } else {
        if (emptyStart && emptyEnd) {
          sections.push({ type: "empty-range", startDate: emptyStart, endDate: emptyEnd });
          emptyStart = null;
          emptyEnd = null;
        }
        sections.push({ type: "day", date: dateStr, tasks: dayTasks, events: dayEvents });
      }
    }
    if (emptyStart && emptyEnd) {
      sections.push({ type: "empty-range", startDate: emptyStart, endDate: emptyEnd });
    }

    return { overdue, daySections: sections, noDueDate, multiDayEvents };
  }, [tasks, events, weekStart, todayStr]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-text-dim" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-sm text-danger mb-3">{error}</p>
        <button onClick={load} className="text-xs text-accent hover:text-accent-hover font-medium">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <WeekNav
        weekStart={weekStart}
        weekEnd={weekEnd}
        onPrev={() => setWeekOffset((o) => o - 1)}
        onNext={() => setWeekOffset((o) => o + 1)}
        onToday={() => setWeekOffset(0)}
      />

      <div className="flex flex-col gap-4">
        {multiDayEvents.map((event, i) => (
          <MultiDayBanner key={`multi-${i}`} event={event} />
        ))}

        {weekOffset === 0 && <OverdueSection tasks={overdue} />}

        {daySections.map((section) => {
          if (section.type === "empty-range") {
            const start = formatDate(section.startDate);
            const end = formatDate(section.endDate);
            const label =
              section.startDate === section.endDate
                ? start
                : `${start} – ${end}`;
            return (
              <div
                key={section.startDate}
                className="rounded-xl border border-border bg-white/[0.01] px-7 py-4"
              >
                <span className="text-xs text-text-dim font-medium">{label} — nothing due</span>
              </div>
            );
          }
          return (
            <DaySection
              key={section.date}
              date={new Date(section.date + "T00:00:00")}
              tasks={section.tasks}
              events={section.events}
            />
          );
        })}

        {noDueDate.length > 0 && (
          <div className="glass-card overflow-clip">
            <div className="px-7 py-4 border-b border-border">
              <span className="text-xs font-bold text-text-dim tracking-tight">
                No Due Date ({noDueDate.length})
              </span>
            </div>
            {noDueDate.map((task, i) => (
              <AgendaTask key={i} task={task} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
