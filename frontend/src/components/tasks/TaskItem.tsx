"use client";

import { Circle, CheckCircle2, MoreHorizontal } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DueBadge } from "./DueBadge";

interface TaskItemProps {
  task: TaskResponse;
}

export function TaskItem({ task }: TaskItemProps): React.JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center gap-3 px-4 py-3 mx-2 rounded-xl",
        "hover:bg-white/[0.03] transition-all duration-150",
        "group cursor-default"
      )}
    >
      {task.completed ? (
        <CheckCircle2 className="w-[18px] h-[18px] text-success shrink-0" />
      ) : (
        <Circle className="w-[18px] h-[18px] text-text-dim shrink-0 group-hover:text-text-muted transition-colors" />
      )}

      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "text-[13px] leading-snug font-medium truncate",
            task.completed ? "text-text-dim line-through" : "text-text"
          )}
        >
          {task.text}
        </p>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {!task.completed && task.days_open > 0 && (
          <span className="text-[10px] text-text-dim font-medium tabular-nums">
            {task.days_open}d open
          </span>
        )}
        <DueBadge dueDate={task.due_date} />

        <button
          aria-label="Task options"
          className="opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 flex items-center justify-center rounded-md hover:bg-white/[0.06] text-text-dim hover:text-text-muted"
        >
          <MoreHorizontal className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
