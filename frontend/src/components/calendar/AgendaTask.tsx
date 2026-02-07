"use client";

import { Circle } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { DueBadge } from "../tasks/DueBadge";

export function AgendaTask({ task }: { task: TaskResponse }) {
  const label = [task.category, task.sub_project].filter(Boolean).join(" > ");

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 hover:bg-card-hover transition-colors border-b border-border/50 last:border-b-0">
      <Circle className="w-3.5 h-3.5 text-text-dim shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-[13px] leading-snug text-text">{task.text}</p>
        {label && (
          <span className="text-[10px] text-text-dim mt-0.5 block">{label}</span>
        )}
      </div>
      <DueBadge dueDate={task.due_date} />
    </div>
  );
}
