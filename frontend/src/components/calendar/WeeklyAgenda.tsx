"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { getTasks, getEvents } from "@/lib/api";
import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { startOfWeek, addDays, toDateStr } from "@/lib/utils";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { WeekNav } from "./WeekNav";
import { WeekGrid } from "./WeekGrid";
import { MultiDayBanner } from "./MultiDayBanner";
import { OverdueSection } from "./OverdueSection";
import { AgendaTask } from "./AgendaTask";
import { DayRibbon } from "./DayRibbon";
import { MobileDayView } from "./MobileDayView";
import { TaskDetailPanel } from "../tasks/TaskDetailPanel";

export function WeeklyAgenda(): React.JSX.Element {
  const isDesktop = useMediaQuery("(min-width: 768px)");

  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [weekOffset, setWeekOffset] = useState(0);
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);
  const [selectedDate, setSelectedDate] = useState(new Date());

  // Smart default: show weekends if today is Saturday or Sunday
  const [showWeekend, setShowWeekend] = useState(() => {
    const day = new Date().getDay();
    return day === 0 || day === 6;
  });

  const weekStart = useMemo(
    () => addDays(startOfWeek(new Date()), weekOffset * 7),
    [weekOffset]
  );
  const weekEnd = addDays(weekStart, 6);
  const weekStartStr = toDateStr(weekStart);
  const weekEndStr = toDateStr(weekEnd);
  const todayStr = toDateStr(new Date());

  // Compute displayed week end for WeekNav label (respects 5d/7d on desktop)
  const displayEnd = isDesktop && !showWeekend ? addDays(weekStart, 4) : weekEnd;

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [taskData, eventData] = await Promise.all([
        getTasks({ completed: false }),
        getEvents(weekStartStr, weekEndStr).catch(() => [] as CalendarEvent[]),
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

  // When week changes, reset selected date
  useEffect(() => {
    if (weekOffset === 0) {
      setSelectedDate(new Date());
    } else {
      setSelectedDate(weekStart);
    }
  }, [weekOffset, weekStart]);

  const handleTaskUpdate = useCallback(() => {
    setSelectedTask(null);
    load();
  }, [load]);

  // Computed data used by both layouts
  const { overdue, multiDayEvents, noDueDate } = useMemo(() => {
    const overdue: TaskResponse[] = [];
    const noDueDate: TaskResponse[] = [];
    const multiDayEvents: CalendarEvent[] = [];

    for (const task of tasks) {
      if (!task.due_date) {
        noDueDate.push(task);
      } else if (task.due_date < todayStr) {
        overdue.push(task);
      }
    }

    for (const event of events) {
      if (event.end_date) {
        multiDayEvents.push(event);
      }
    }

    return { overdue, multiDayEvents, noDueDate };
  }, [tasks, events, todayStr]);

  // Mobile: events + tasks for the selected day
  const { selectedDayEvents, selectedDayTasks } = useMemo(() => {
    const ds = toDateStr(selectedDate);

    const selectedDayEvents = events.filter((e) => {
      const start = e.date;
      const end = e.end_date || e.date;
      return ds >= start && ds <= end;
    });

    const selectedDayTasks = tasks.filter((t) => t.due_date === ds);

    return { selectedDayEvents, selectedDayTasks };
  }, [events, tasks, selectedDate]);

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
        weekEnd={displayEnd}
        onPrev={() => setWeekOffset((o) => o - 1)}
        onNext={() => setWeekOffset((o) => o + 1)}
        onToday={() => setWeekOffset(0)}
        showWeekend={showWeekend}
        onToggleWeekend={setShowWeekend}
      />

      {isDesktop ? (
        /* ===== Desktop: grid layout ===== */
        <div className="flex flex-col gap-4">
          {multiDayEvents.map((event, i) => (
            <MultiDayBanner key={`multi-${i}`} event={event} />
          ))}

          <WeekGrid
            weekStart={weekStart}
            tasks={tasks}
            events={events}
            showWeekend={showWeekend}
            onTaskUpdate={handleTaskUpdate}
            onTaskSelect={setSelectedTask}
          />

          {weekOffset === 0 && (
            <OverdueSection
              tasks={overdue}
              onTaskUpdate={handleTaskUpdate}
              onTaskSelect={setSelectedTask}
            />
          )}

          {noDueDate.length > 0 && (
            <div className="glass-card overflow-clip">
              <div className="px-7 py-4 border-b border-border">
                <span className="text-xs font-bold text-text-dim tracking-tight">
                  No Due Date ({noDueDate.length})
                </span>
              </div>
              {noDueDate.map((task, i) => (
                <AgendaTask
                  key={i}
                  task={task}
                  onUpdate={handleTaskUpdate}
                  onSelect={setSelectedTask}
                />
              ))}
            </div>
          )}
        </div>
      ) : (
        /* ===== Mobile: day-picker ribbon + single-day view ===== */
        <div>
          <DayRibbon
            weekStart={weekStart}
            tasks={tasks}
            events={events}
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
          />
          <MobileDayView
            date={selectedDate}
            events={selectedDayEvents}
            tasks={selectedDayTasks}
            overdueTasks={overdue}
            onTaskUpdate={handleTaskUpdate}
            onTaskSelect={setSelectedTask}
          />
        </div>
      )}

      {selectedTask && (
        <TaskDetailPanel
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onUpdate={handleTaskUpdate}
        />
      )}
    </div>
  );
}
