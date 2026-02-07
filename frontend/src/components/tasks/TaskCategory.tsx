"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { TaskSubProject } from "./TaskSubProject";

interface TaskCategoryProps {
  category: string;
  tasks: TaskResponse[];
}

export function TaskCategory({ category, tasks }: TaskCategoryProps) {
  const [expanded, setExpanded] = useState(true);
  const openCount = tasks.filter((t) => !t.completed).length;

  // Group by sub_project
  const grouped = new Map<string, TaskResponse[]>();
  for (const task of tasks) {
    const key = task.sub_project || "";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(task);
  }

  return (
    <div className="glass-card overflow-hidden transition-all duration-200">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-3 w-full px-5 py-4 hover:bg-white/[0.02] transition-all"
      >
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-text-dim" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-dim" />
        )}
        <span className="text-sm font-bold text-text tracking-tight">{category}</span>
        <span className="ml-auto text-[11px] font-semibold text-accent bg-accent/10 px-2.5 py-1 rounded-lg shadow-[0_0_10px_rgba(79,142,247,0.1)]">
          {openCount} open
        </span>
      </button>
      {expanded && (
        <div className="border-t border-border">
          {Array.from(grouped.entries()).map(([sub, subTasks]) => (
            <TaskSubProject key={sub || "__none"} name={sub} tasks={subTasks} />
          ))}
        </div>
      )}
    </div>
  );
}
