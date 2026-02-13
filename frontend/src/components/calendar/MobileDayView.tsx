"use client";

import type { TaskResponse, CalendarEvent } from "@/lib/types";
import { toDateStr } from "@/lib/utils";
import { AgendaTask } from "./AgendaTask";
import { AgendaEvent } from "./AgendaEvent";
import { OverdueSection } from "./OverdueSection";

interface MobileDayViewProps {
  date: Date;
  events: CalendarEvent[];
  tasks: TaskResponse[];
  overdueTasks: TaskResponse[];
  onTaskUpdate?: () => void;
  onTaskSelect?: (task: TaskResponse) => void;
}

export function MobileDayView({
  date,
  events,
  tasks,
  overdueTasks,
  onTaskUpdate,
  onTaskSelect,
}: MobileDayViewProps): React.JSX.Element {
  const todayStr = toDateStr(new Date());
  const dateStr = toDateStr(date);
  const isToday = dateStr === todayStr;
  const dayLabel = date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });

  const hasContent = events.length > 0 || tasks.length > 0;

  return (
    <div className="space-y-4 pt-4">
      <p className="text-sm font-medium text-text-dim px-1">{dayLabel}</p>

      {!hasContent && !isToday && (
        <div className="glass-card p-8 text-center">
          <p className="text-xs text-text-dim">Nothing scheduled</p>
        </div>
      )}

      {events.length > 0 && (
        <div className="glass-card overflow-clip">
          {events.map((event) => (
            <AgendaEvent key={`event-${event.title}-${event.time}`} event={event} />
          ))}
        </div>
      )}

      {tasks.length > 0 && (
        <div className="glass-card overflow-clip">
          {tasks.map((task) => (
            <AgendaTask
              key={`task-${task.text}`}
              task={task}
              onUpdate={onTaskUpdate}
              onSelect={onTaskSelect}
            />
          ))}
        </div>
      )}

      {isToday && (
        <OverdueSection
          tasks={overdueTasks}
          onTaskUpdate={onTaskUpdate}
          onTaskSelect={onTaskSelect}
        />
      )}
    </div>
  );
}
