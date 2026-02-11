"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CircleDot, AlertTriangle, Clock, CheckCircle2, Loader } from "lucide-react";
import { getTasks } from "@/lib/api";
import type { TaskResponse } from "@/lib/types";
import { cn, toDateStr } from "@/lib/utils";
import { TaskCategory } from "./TaskCategory";
import { TaskFilters } from "./TaskFilters";
import { TaskDetailPanel } from "./TaskDetailPanel";

type StatColor = "accent" | "danger" | "warning" | "success" | "info";
export type StatFilter = "active" | "overdue" | "dueToday" | "inProgress" | "completed";

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  color: StatColor;
  isActive: boolean;
  onClick: () => void;
}

const STAT_COLORS: Record<StatColor, { icon: string; iconBg: string; value: string; glow: string }> = {
  accent: {
    icon: "text-accent",
    iconBg: "bg-accent/12",
    value: "text-accent",
    glow: "shadow-[0_0_20px_rgba(79,142,247,0.06)]",
  },
  danger: {
    icon: "text-danger",
    iconBg: "bg-danger/12",
    value: "text-danger",
    glow: "shadow-[0_0_20px_rgba(248,113,113,0.06)]",
  },
  warning: {
    icon: "text-warning",
    iconBg: "bg-warning/12",
    value: "text-warning",
    glow: "shadow-[0_0_20px_rgba(251,191,36,0.06)]",
  },
  success: {
    icon: "text-success",
    iconBg: "bg-success/12",
    value: "text-success",
    glow: "shadow-[0_0_20px_rgba(52,211,153,0.06)]",
  },
  info: {
    icon: "text-accent",
    iconBg: "bg-accent/12",
    value: "text-accent",
    glow: "shadow-[0_0_20px_rgba(79,142,247,0.06)]",
  },
};

function StatCard({ icon: Icon, label, value, color, isActive, onClick }: StatCardProps): React.JSX.Element {
  const colors = STAT_COLORS[color];

  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={onClick}
      className={cn(
        "stat-card-v2 flex flex-col gap-2 text-left transition-all duration-200 focus-ring active:translate-y-0",
        colors.glow,
        isActive && "ring-1 ring-accent/30 border-accent/20"
      )}
    >
      <div className="flex items-center justify-between">
        <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center", colors.iconBg)}>
          <Icon className={cn("w-5 h-5", colors.icon)} />
        </div>
        <span className={cn("text-[32px] font-bold tracking-tight", colors.value)}>{value}</span>
      </div>
      <span className="text-[11px] font-medium text-text-dim uppercase tracking-wider mt-1">{label}</span>
    </button>
  );
}

export function TaskTree(): React.JSX.Element {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState<StatFilter | null>(null);
  const [selectedTask, setSelectedTask] = useState<TaskResponse | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getTasks();
      setTasks(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tasks");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleTaskUpdate = useCallback(() => {
    setSelectedTask(null);
    load();
  }, [load]);

  const todayStr = toDateStr(new Date());

  const stats = useMemo(() => {
    const open = tasks.filter((t) => !t.completed);
    const overdue = open.filter((t) => t.due_date && t.due_date < todayStr);
    const dueToday = open.filter((t) => t.due_date === todayStr);
    const inProgress = tasks.filter((t) => t.status === "in_progress");
    const completed = tasks.filter((t) => t.completed);
    return { open: open.length, overdue: overdue.length, dueToday: dueToday.length, inProgress: inProgress.length, completed: completed.length };
  }, [tasks, todayStr]);

  const toggleFilter = useCallback((filter: StatFilter) => {
    setActiveFilter((prev) => (prev === filter ? null : filter));
    if (filter === "completed") setShowCompleted(true);
  }, []);

  const clearFilter = useCallback(() => {
    setActiveFilter(null);
  }, []);

  const filtered = useMemo(() => {
    let result = tasks;

    // Apply stat card filter
    switch (activeFilter) {
      case "active":
        result = result.filter((t) => !t.completed);
        break;
      case "overdue":
        result = result.filter((t) => !t.completed && !!t.due_date && t.due_date < todayStr);
        break;
      case "dueToday":
        result = result.filter((t) => !t.completed && t.due_date === todayStr);
        break;
      case "inProgress":
        result = result.filter((t) => t.status === "in_progress");
        break;
      case "completed":
        result = result.filter((t) => t.completed);
        break;
      default:
        if (!showCompleted) {
          result = result.filter((t) => !t.completed);
        }
        break;
    }

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (t) =>
          t.text.toLowerCase().includes(q) ||
          t.category.toLowerCase().includes(q) ||
          t.sub_project.toLowerCase().includes(q)
      );
    }
    return result;
  }, [tasks, showCompleted, search, activeFilter, todayStr]);

  const categories = useMemo(() => {
    const map = new Map<string, TaskResponse[]>();
    for (const task of filtered) {
      const cat = task.category || "Uncategorized";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(task);
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  if (loading) {
    return (
      <div>
        {/* Stat cards skeleton */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-5 mb-10">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="stat-card-v2 h-[100px]">
              <div className="flex items-center justify-between mb-3">
                <div className="w-9 h-9 rounded-xl skeleton-shimmer" />
                <div className="w-10 h-7 rounded-lg skeleton-shimmer" />
              </div>
              <div className="w-16 h-3 rounded skeleton-shimmer" />
            </div>
          ))}
        </div>

        {/* Search skeleton */}
        <div className="h-11 rounded-xl skeleton-shimmer border border-border mb-8" />

        {/* Category skeletons */}
        {[...Array(3)].map((_, i) => (
          <div key={i} className="glass-card mb-5 p-5">
            <div className="flex items-center gap-3">
              <div className="w-4 h-4 rounded skeleton-shimmer" />
              <div className="w-24 h-4 rounded skeleton-shimmer" />
              <div className="ml-auto w-14 h-5 rounded-lg skeleton-shimmer" />
            </div>
            <div className="mt-4 space-y-1">
              {[...Array(3 - i)].map((_, j) => (
                <div key={j} className="flex items-center gap-3 px-4 py-3">
                  <div className="w-[18px] h-[18px] rounded-full skeleton-shimmer" />
                  <div className="flex-1 h-3.5 rounded skeleton-shimmer" />
                  <div className="w-14 h-5 rounded-lg skeleton-shimmer" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-sm text-danger mb-3">{error}</p>
        <button
          onClick={load}
          className="text-xs text-accent hover:text-accent-hover font-medium"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Stat cards row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-5 mb-10">
        <StatCard icon={CircleDot} label="Active" value={stats.open} color="accent" isActive={activeFilter === "active"} onClick={() => toggleFilter("active")} />
        <StatCard icon={AlertTriangle} label="Overdue" value={stats.overdue} color="danger" isActive={activeFilter === "overdue"} onClick={() => toggleFilter("overdue")} />
        <StatCard icon={Clock} label="Due Today" value={stats.dueToday} color="warning" isActive={activeFilter === "dueToday"} onClick={() => toggleFilter("dueToday")} />
        <StatCard icon={Loader} label="In Progress" value={stats.inProgress} color="info" isActive={activeFilter === "inProgress"} onClick={() => toggleFilter("inProgress")} />
        <StatCard icon={CheckCircle2} label="Completed" value={stats.completed} color="success" isActive={activeFilter === "completed"} onClick={() => toggleFilter("completed")} />
      </div>

      <TaskFilters
        showCompleted={showCompleted}
        onToggleCompleted={() => setShowCompleted(!showCompleted)}
        search={search}
        onSearchChange={setSearch}
        activeFilter={activeFilter}
        onClearFilter={clearFilter}
      />
      {categories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
            <CheckCircle2 className="w-7 h-7 text-accent/60" />
          </div>
          <p className="text-sm font-medium text-text-muted mb-1">All clear</p>
          <p className="text-xs text-text-dim">No tasks match your current filters.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {categories.map(([cat, catTasks]) => (
            <TaskCategory key={cat} category={cat} tasks={catTasks} onUpdate={handleTaskUpdate} onSelect={setSelectedTask} />
          ))}
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
