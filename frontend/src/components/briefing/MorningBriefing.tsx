"use client";

import { useEffect, useState } from "react";
import {
  Calendar,
  AlertTriangle,
  Target,
  BookOpen,
  Hourglass,
  CheckCircle2,
  RefreshCw,
  Circle,
  Clock,
  Sun,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getBriefing } from "@/lib/api";
import type { BriefingResponse, BriefingTask, CalendarEvent } from "@/lib/types";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good Morning";
  if (hour < 17) return "Good Afternoon";
  return "Good Evening";
}

function formatContextDate(dateStr: string): string {
  const date = new Date(dateStr + "T00:00:00");
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function BriefingTaskItem({ task }: { task: BriefingTask }): React.JSX.Element {
  return (
    <div className="flex items-center gap-3 py-2">
      <Circle className="w-4 h-4 text-text-dim shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-text font-medium break-words">{task.text}</p>
        {task.category && (
          <p className="text-[11px] text-text-dim mt-0.5">
            {task.category}
            {task.sub_project ? ` / ${task.sub_project}` : ""}
          </p>
        )}
      </div>
      {task.days_open > 0 && (
        <span className="text-[10px] text-text-dim font-medium tabular-nums shrink-0">
          {task.days_open}d open
        </span>
      )}
      {task.due_date && (
        <span className="text-[10px] text-text-dim font-medium shrink-0">
          {task.due_date}
        </span>
      )}
    </div>
  );
}

function TaskSection({
  icon: Icon,
  title,
  tasks,
  iconColor,
  titleColor,
  borderStyle,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  tasks: BriefingTask[];
  iconColor: string;
  titleColor: string;
  borderStyle?: React.CSSProperties;
}): React.JSX.Element | null {
  if (tasks.length === 0) return null;

  return (
    <div
      className={cn("glass-card p-5", titleColor === "text-danger" && "glass-card-danger")}
      style={borderStyle}
    >
      <div className="flex items-center gap-2 mb-3">
        <Icon className={cn("w-4.5 h-4.5", iconColor)} />
        <h2 className={cn("text-sm font-semibold", titleColor)}>
          {title} ({tasks.length})
        </h2>
      </div>
      <div className="divide-y divide-border">
        {tasks.map((task, i) => (
          <BriefingTaskItem key={i} task={task} />
        ))}
      </div>
    </div>
  );
}

function StatCard({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: "danger" | "warning" | "accent" | "success";
}): React.JSX.Element {
  const colorMap = {
    danger: {
      text: "text-danger",
      glow: "shadow-[0_0_12px_rgba(248,113,113,0.1)]",
    },
    warning: {
      text: "text-warning",
      glow: "shadow-[0_0_12px_rgba(251,191,36,0.1)]",
    },
    accent: {
      text: "text-accent",
      glow: "shadow-[0_0_12px_rgba(79,142,247,0.1)]",
    },
    success: {
      text: "text-success",
      glow: "shadow-[0_0_12px_rgba(52,211,153,0.1)]",
    },
  };
  const c = colorMap[color];

  return (
    <div className={cn("glass-card p-4 flex flex-col items-center gap-1", c.glow)}>
      <span className={cn("text-2xl font-bold tabular-nums", c.text)}>{count}</span>
      <span className="text-[11px] text-text-dim font-medium">{label}</span>
    </div>
  );
}

function BriefingSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 w-64 skeleton-shimmer rounded-lg" />
      <div className="h-5 w-48 skeleton-shimmer rounded-md" />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="glass-card p-4 h-20 skeleton-shimmer" />
        ))}
      </div>
      <div className="glass-card p-6 h-40 skeleton-shimmer" />
      <div className="glass-card p-6 h-32 skeleton-shimmer" />
    </div>
  );
}

function BriefingError({ onRetry }: { onRetry: () => void }): React.JSX.Element {
  return (
    <div className="glass-card p-8 text-center">
      <AlertTriangle className="w-8 h-8 text-warning mx-auto mb-3" />
      <p className="text-sm text-text-muted mb-4">Failed to load briefing data</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-accent bg-accent-glow rounded-lg hover:bg-accent/20 transition-colors"
      >
        <RefreshCw className="w-4 h-4" />
        Retry
      </button>
    </div>
  );
}

function ContextList({
  label,
  items,
  dotColor,
}: {
  label: string;
  items: string[];
  dotColor: string;
}): React.JSX.Element | null {
  if (items.length === 0) return null;

  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-text-dim font-medium mb-1.5">
        {label}
      </p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] text-text-muted">
            <span className={cn("w-1.5 h-1.5 rounded-full mt-1.5 shrink-0", dotColor)} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatEventTime(time: string): string {
  if (!time) return "All day";
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  const hour12 = h % 12 || 12;
  return `${hour12}:${m.toString().padStart(2, "0")} ${suffix}`;
}

function TodayView({
  events,
  focusItems,
  dueCount,
}: {
  events: CalendarEvent[];
  focusItems: string[];
  dueCount: number;
}): React.JSX.Element | null {
  const hasEvents = events.length > 0;
  const hasFocus = focusItems.length > 0;

  if (!hasEvents && !hasFocus && dueCount === 0) return null;

  // Sort events by time (timed first, then all-day)
  const sorted = [...events].sort((a, b) => {
    if (a.time && !b.time) return -1;
    if (!a.time && b.time) return 1;
    return a.time.localeCompare(b.time);
  });

  return (
    <div className="glass-card p-5" style={{ borderColor: "rgba(251, 191, 36, 0.2)" }}>
      <div className="flex items-center gap-2 mb-3">
        <Sun className="w-4.5 h-4.5 text-warning" />
        <h2 className="text-sm font-semibold text-text">Today&apos;s View</h2>
        {dueCount > 0 && (
          <span className="ml-auto text-[11px] text-warning font-medium">
            {dueCount} task{dueCount !== 1 ? "s" : ""} due
          </span>
        )}
      </div>

      <div className="space-y-3">
        {/* Calendar events */}
        {hasEvents && (
          <div>
            <p className="text-[11px] uppercase tracking-wider text-text-dim font-medium mb-1.5">
              Schedule
            </p>
            <div className="space-y-1">
              {sorted.map((event, i) => (
                <div key={i} className="flex items-center gap-2 text-[13px] text-text-muted">
                  <Clock className="w-3 h-3 text-text-dim shrink-0" />
                  <span className="text-[11px] text-text-dim font-medium w-16 shrink-0">
                    {formatEventTime(event.time)}
                  </span>
                  <span className="break-words">{event.title}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Focus items from today's daily note */}
        {hasFocus && (
          <div>
            <p className="text-[11px] uppercase tracking-wider text-text-dim font-medium mb-1.5">
              Focus
            </p>
            <ul className="space-y-1">
              {focusItems.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-[13px] text-text-muted">
                  <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 bg-warning" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export function MorningBriefing(): React.JSX.Element {
  const [data, setData] = useState<BriefingResponse | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchBriefing = async () => {
    setLoading(true);
    setError(false);
    try {
      const result = await getBriefing();
      setData(result);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBriefing();
  }, []);

  // Shared page shell wraps all states
  function renderContent(): React.JSX.Element {
    if (loading) return <BriefingSkeleton />;
    if (error || !data) return <BriefingError onRetry={fetchBriefing} />;
    return <BriefingContent data={data} />;
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-8 pt-6 pb-2">
        <h1 className="text-xl font-bold text-text tracking-tight">{getGreeting()}</h1>
        {data && !loading && (
          <div className="flex items-center gap-2 mt-1">
            <Calendar className="w-4 h-4 text-accent" />
            <p className="text-[13px] text-text-muted">{data.today_display}</p>
            <span className="text-[11px] text-text-dim ml-2">
              {data.total_open} open task{data.total_open !== 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>
      <div className="overflow-y-auto flex-1 px-4 md:px-8 pb-6 pt-4">
        {renderContent()}
      </div>
    </div>
  );
}

function BriefingContent({ data }: { data: BriefingResponse }): React.JSX.Element {
  const hasUrgent =
    data.overdue_tasks.length > 0 ||
    data.due_today_tasks.length > 0 ||
    data.aging_followups.length > 0;

  return (
    <div className="space-y-5">
      {/* Today's view */}
      <TodayView
        events={data.today_events}
        focusItems={data.today_context?.focus_items ?? []}
        dueCount={data.due_today_tasks.length}
      />

      {/* Stat row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Overdue" count={data.overdue_tasks.length} color="danger" />
        <StatCard label="Due Today" count={data.due_today_tasks.length} color="warning" />
        <StatCard label="Aging" count={data.aging_followups.length} color="accent" />
        <StatCard label="Total Open" count={data.total_open} color="success" />
      </div>

      {/* Task sections */}
      <TaskSection
        icon={AlertTriangle}
        title="Overdue"
        tasks={data.overdue_tasks}
        iconColor="text-danger"
        titleColor="text-danger"
      />
      <TaskSection
        icon={Target}
        title="Due Today"
        tasks={data.due_today_tasks}
        iconColor="text-warning"
        titleColor="text-warning"
        borderStyle={{ borderColor: "rgba(251, 191, 36, 0.2)" }}
      />

      {/* Yesterday's context */}
      {data.yesterday_context && (
        <div className="glass-card p-5">
          <div className="flex items-center gap-2 mb-1">
            <BookOpen className="w-4.5 h-4.5 text-purple" />
            <h2 className="text-sm font-semibold text-text">Yesterday&apos;s Context</h2>
          </div>
          <p className="text-[11px] text-text-dim mb-3 ml-6">
            Based on {formatContextDate(data.yesterday_context.date)}
          </p>
          <div className="space-y-3 ml-1">
            <ContextList
              label="Focus"
              items={data.yesterday_context.focus_items}
              dotColor="bg-purple"
            />
            <ContextList
              label="Notes"
              items={data.yesterday_context.notes_items}
              dotColor="bg-text-dim"
            />
          </div>
        </div>
      )}

      {/* Aging follow-ups */}
      <TaskSection
        icon={Hourglass}
        title="Aging Follow-ups"
        tasks={data.aging_followups}
        iconColor="text-accent"
        titleColor="text-text"
        borderStyle={{ borderColor: "rgba(79, 142, 247, 0.15)" }}
      />

      {/* All-clear state */}
      {!hasUrgent && (
        <div className="glass-card p-8 text-center">
          <CheckCircle2 className="w-10 h-10 text-success mx-auto mb-3 drop-shadow-[0_0_8px_rgba(52,211,153,0.3)]" />
          <p className="text-sm font-semibold text-text">All clear</p>
          <p className="text-[12px] text-text-muted mt-1">
            No overdue tasks, nothing due today, and no aging follow-ups.
          </p>
        </div>
      )}
    </div>
  );
}
