"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { TaskItem } from "./TaskItem";

interface TaskSubProjectProps {
  name: string;
  tasks: TaskResponse[];
}

export function TaskSubProject({ name, tasks }: TaskSubProjectProps) {
  const [expanded, setExpanded] = useState(true);
  const openCount = tasks.filter((t) => !t.completed).length;

  if (!name) {
    return (
      <div className="flex flex-col">
        {tasks.map((task, i) => (
          <TaskItem key={i} task={task} />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-5 py-2.5 text-xs text-text-muted hover:text-text hover:bg-white/[0.02] transition-all duration-150 border-b border-border"
      >
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        <span className="font-medium">{name}</span>
        <span className="text-text-dim ml-auto">{openCount}</span>
      </button>
      {expanded && (
        <div className="flex flex-col">
          {tasks.map((task, i) => (
            <TaskItem key={i} task={task} />
          ))}
        </div>
      )}
    </div>
  );
}
