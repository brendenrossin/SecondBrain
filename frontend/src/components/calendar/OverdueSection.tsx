"use client";

import { AlertTriangle } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { AgendaTask } from "./AgendaTask";

export function OverdueSection({ tasks }: { tasks: TaskResponse[] }) {
  if (tasks.length === 0) return null;

  return (
    <div className="glass-card glass-card-danger overflow-clip">
      <div className="flex items-center gap-2 px-7 py-4 border-b border-danger/15">
        <AlertTriangle className="w-4 h-4 text-danger drop-shadow-[0_0_6px_rgba(248,113,113,0.4)]" />
        <span className="text-xs font-bold text-danger">
          Overdue
        </span>
        <span className="ml-auto text-[10px] font-semibold text-danger bg-danger-dim px-2.5 py-0.5 rounded-lg shadow-[0_0_8px_rgba(248,113,113,0.1)]">
          {tasks.length} task{tasks.length !== 1 ? "s" : ""}
        </span>
      </div>
      {tasks.map((task, i) => (
        <AgendaTask key={i} task={task} />
      ))}
    </div>
  );
}
