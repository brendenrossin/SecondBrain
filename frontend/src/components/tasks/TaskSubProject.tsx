"use client";

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskResponse } from "@/lib/types";
import { TaskItem } from "./TaskItem";

interface TaskSubProjectProps {
  name: string;
  tasks: TaskResponse[];
  onUpdate?: () => void;
  onSelect?: (task: TaskResponse) => void;
}

export function TaskSubProject({ name, tasks, onUpdate, onSelect }: TaskSubProjectProps): React.JSX.Element {
  const [expanded, setExpanded] = useState(true);
  const openCount = tasks.filter((t) => !t.completed).length;

  if (!name) {
    return (
      <div className="flex flex-col">
        {tasks.map((task, i) => (
          <TaskItem key={i} task={task} onUpdate={onUpdate} onSelect={onSelect} />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-5 py-3 text-xs text-text-muted hover:text-text hover:bg-white/[0.03] transition-all duration-150"
      >
        <ChevronRight
          className={cn(
            "w-3 h-3 transition-transform duration-200",
            expanded && "rotate-90"
          )}
        />
        <span className="font-medium">{name}</span>
        <span className="text-text-dim ml-auto">{openCount}</span>
      </button>
      <div className={cn("accordion-body", expanded && "expanded")}>
        <div>
          <div className="flex flex-col">
            {tasks.map((task, i) => (
              <TaskItem key={i} task={task} onUpdate={onUpdate} onSelect={onSelect} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
