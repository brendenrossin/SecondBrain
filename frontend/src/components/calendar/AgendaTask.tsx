"use client";

import { useState } from "react";
import type { TaskResponse } from "@/lib/types";
import { updateTask } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DueBadge } from "../tasks/DueBadge";
import { StatusIcon } from "../tasks/StatusIcon";

interface AgendaTaskProps {
  task: TaskResponse;
  onUpdate?: () => void;
  onSelect?: (task: TaskResponse) => void;
}

export function AgendaTask({ task, onUpdate, onSelect }: AgendaTaskProps): React.JSX.Element {
  const [updating, setUpdating] = useState(false);
  const label = [task.category, task.sub_project].filter(Boolean).join(" > ");

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
        "flex items-center gap-3.5 px-7 py-4 hover:bg-card-hover transition-colors border-b border-border/50 last:border-b-0",
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
      <div className="flex-1 min-w-0">
        <p className={cn(
          "text-[13px] leading-snug",
          task.status === "done" ? "text-text-dim line-through" : "text-text"
        )}>{task.text}</p>
        {label && (
          <span className="text-[10px] text-text-dim mt-0.5 block">{label}</span>
        )}
      </div>
      <DueBadge dueDate={task.due_date} />
    </div>
  );
}
