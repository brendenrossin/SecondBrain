"use client";

import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskResponse } from "@/lib/types";
import { TaskSubProject } from "./TaskSubProject";

function sortTasksByDueDate(tasks: TaskResponse[]): TaskResponse[] {
  return [...tasks].sort((a, b) => {
    if (!a.due_date && !b.due_date) return 0;
    if (!a.due_date) return 1;
    if (!b.due_date) return -1;
    return a.due_date.localeCompare(b.due_date);
  });
}

function earliestDueDate(tasks: TaskResponse[]): string | null {
  const dates = tasks.map((t) => t.due_date).filter(Boolean) as string[];
  return dates.length > 0 ? dates.sort()[0] : null;
}

interface TaskCategoryProps {
  category: string;
  tasks: TaskResponse[];
  onUpdate?: () => void;
  onSelect?: (task: TaskResponse) => void;
}

export function TaskCategory({ category, tasks, onUpdate, onSelect }: TaskCategoryProps): React.JSX.Element {
  const [expanded, setExpanded] = useState(true);
  const openCount = tasks.filter((t) => !t.completed).length;

  // Group by sub_project, sort tasks within each group by due date,
  // then sort sub-project groups by most urgent task
  const sortedGroups = useMemo(() => {
    const grouped = new Map<string, TaskResponse[]>();
    for (const task of tasks) {
      const key = task.sub_project || "";
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(task);
    }

    // Sort tasks within each group
    const entries = Array.from(grouped.entries()).map(
      ([key, groupTasks]) => [key, sortTasksByDueDate(groupTasks)] as [string, TaskResponse[]]
    );

    // Sort sub-project groups by urgency
    entries.sort(([, tasksA], [, tasksB]) => {
      const urgA = earliestDueDate(tasksA);
      const urgB = earliestDueDate(tasksB);
      if (!urgA && !urgB) return tasksB.length - tasksA.length;
      if (!urgA) return 1;
      if (!urgB) return -1;
      const cmp = urgA.localeCompare(urgB);
      if (cmp !== 0) return cmp;
      return tasksB.length - tasksA.length;
    });

    return entries;
  }, [tasks]);

  return (
    <div className="glass-card overflow-clip transition-all duration-200">
      <button
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center gap-3 w-full px-6 py-4.5 hover:bg-white/[0.03] transition-all"
      >
        <ChevronRight
          className={cn(
            "w-4 h-4 text-text-dim transition-transform duration-200",
            expanded && "rotate-90"
          )}
        />
        <span className="text-sm font-bold text-text tracking-tight">{category}</span>
        <span className="ml-auto text-[11px] font-semibold text-accent bg-accent/10 px-2.5 py-1 rounded-lg shadow-[0_0_10px_rgba(79,142,247,0.1)]">
          {openCount} open
        </span>
      </button>
      <div className={cn("accordion-body", expanded && "expanded")}>
        <div>
          <div className="px-3 pb-3">
            {sortedGroups.map(([sub, subTasks]) => (
              <TaskSubProject key={sub || "__none"} name={sub} tasks={subTasks} onUpdate={onUpdate} onSelect={onSelect} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
