"use client";

import { useState } from "react";
import type { TaskResponse } from "@/lib/types";
import { updateTask } from "@/lib/api";
import { cn, daysUntil } from "@/lib/utils";
import { StatusIcon } from "../tasks/StatusIcon";

interface CompactTaskProps {
  task: TaskResponse;
  onUpdate?: () => void;
  onSelect?: (task: TaskResponse) => void;
}

function dueDotColor(dueDate: string): string | null {
  if (!dueDate) return null;
  const days = daysUntil(dueDate);
  if (days < 0) return "bg-danger";
  if (days === 0) return "bg-warning";
  if (days <= 3) return "bg-accent";
  return null;
}

export function CompactTask({ task, onUpdate, onSelect }: CompactTaskProps): React.JSX.Element {
  const [updating, setUpdating] = useState(false);
  const dot = dueDotColor(task.due_date);

  async function handleToggle(e: React.MouseEvent) {
    e.stopPropagation();
    if (updating) return;
    setUpdating(true);
    try {
      await updateTask({
        text: task.text,
        category: task.category,
        sub_project: task.sub_project,
        status: task.status === "done" ? "open" : "done",
      });
      onUpdate?.();
    } catch {
      // silently fail
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div
      onClick={() => onSelect?.(task)}
      className={cn(
        "flex items-center gap-1.5 px-2 py-1.5 rounded-lg hover:bg-white/[0.03] transition-colors",
        onSelect && "cursor-pointer",
        updating && "opacity-60 pointer-events-none"
      )}
    >
      <button
        onClick={handleToggle}
        className="shrink-0 focus-ring rounded-full"
        aria-label={task.status === "done" ? "Mark incomplete" : "Mark complete"}
      >
        <StatusIcon status={task.status} size="sm" />
      </button>
      <span
        className={cn(
          "text-xs leading-snug truncate flex-1 min-w-0",
          task.status === "done" ? "text-text-dim line-through" : "text-text"
        )}
      >
        {task.text}
      </span>
      {dot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)} />}
    </div>
  );
}
