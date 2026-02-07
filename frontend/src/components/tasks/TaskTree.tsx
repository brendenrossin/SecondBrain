"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, CircleDot, AlertTriangle, Clock, CheckCircle2 } from "lucide-react";
import { getTasks } from "@/lib/api";
import type { TaskResponse } from "@/lib/types";
import { toDateStr } from "@/lib/utils";
import { TaskCategory } from "./TaskCategory";
import { TaskFilters } from "./TaskFilters";

type StatColor = "accent" | "danger" | "warning" | "success";

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  color: StatColor;
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
};

function StatCard({ icon: Icon, label, value, color }: StatCardProps): React.JSX.Element {
  const colors = STAT_COLORS[color];

  return (
    <div className={`stat-card-v2 flex flex-col gap-2 ${colors.glow}`}>
      <div className="flex items-center justify-between">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${colors.iconBg}`}>
          <Icon className={`w-4.5 h-4.5 ${colors.icon}`} />
        </div>
        <span className={`text-[28px] font-bold tracking-tight ${colors.value}`}>{value}</span>
      </div>
      <span className="text-[11px] font-medium text-text-dim uppercase tracking-wider">{label}</span>
    </div>
  );
}

export function TaskTree(): React.JSX.Element {
  const [tasks, setTasks] = useState<TaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCompleted, setShowCompleted] = useState(false);
  const [search, setSearch] = useState("");

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

  const todayStr = toDateStr(new Date());

  const stats = useMemo(() => {
    const open = tasks.filter((t) => !t.completed);
    const overdue = open.filter((t) => t.due_date && t.due_date < todayStr);
    const dueToday = open.filter((t) => t.due_date === todayStr);
    const completed = tasks.filter((t) => t.completed);
    return { open: open.length, overdue: overdue.length, dueToday: dueToday.length, completed: completed.length };
  }, [tasks, todayStr]);

  const filtered = useMemo(() => {
    let result = tasks;
    if (!showCompleted) {
      result = result.filter((t) => !t.completed);
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
  }, [tasks, showCompleted, search]);

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
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-accent" />
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard icon={CircleDot} label="Active" value={stats.open} color="accent" />
        <StatCard icon={AlertTriangle} label="Overdue" value={stats.overdue} color="danger" />
        <StatCard icon={Clock} label="Due Today" value={stats.dueToday} color="warning" />
        <StatCard icon={CheckCircle2} label="Completed" value={stats.completed} color="success" />
      </div>

      <TaskFilters
        showCompleted={showCompleted}
        onToggleCompleted={() => setShowCompleted(!showCompleted)}
        search={search}
        onSearchChange={setSearch}
      />
      {categories.length === 0 ? (
        <p className="text-sm text-text-dim text-center py-12">No tasks found</p>
      ) : (
        <div className="flex flex-col gap-4">
          {categories.map(([cat, catTasks]) => (
            <TaskCategory key={cat} category={cat} tasks={catTasks} />
          ))}
        </div>
      )}
    </div>
  );
}
