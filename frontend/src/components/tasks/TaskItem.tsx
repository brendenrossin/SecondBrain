"use client";

import { Circle, CheckCircle2 } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DueBadge } from "./DueBadge";

export function TaskItem({ task }: { task: TaskResponse }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.02] transition-all duration-150 border-b border-border last:border-b-0">
      {task.completed ? (
        <CheckCircle2 className="w-4 h-4 text-success shrink-0 drop-shadow-[0_0_4px_rgba(52,211,153,0.3)]" />
      ) : (
        <Circle className="w-4 h-4 text-text-dim shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "text-[13px] leading-relaxed font-medium",
            task.completed ? "text-text-dim line-through" : "text-text"
          )}
        >
          {task.text}
        </p>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        {!task.completed && task.days_open > 0 && (
          <span className="text-[10px] text-text-dim font-medium">{task.days_open}d open</span>
        )}
        <DueBadge dueDate={task.due_date} />
      </div>
    </div>
  );
}
