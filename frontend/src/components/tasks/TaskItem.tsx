"use client";

import { useEffect, useRef, useState } from "react";
import { Circle, CheckCircle2, MoreHorizontal, ExternalLink } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DueBadge } from "./DueBadge";

interface TaskItemProps {
  task: TaskResponse;
}

export function TaskItem({ task }: TaskItemProps): React.JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (
        menuRef.current && !menuRef.current.contains(e.target as Node) &&
        buttonRef.current && !buttonRef.current.contains(e.target as Node)
      ) {
        setMenuOpen(false);
      }
    }

    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

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

        <div className="relative">
          <button
            ref={buttonRef}
            aria-label="Task options"
            onClick={() => setMenuOpen((v) => !v)}
            className={cn(
              "transition-opacity w-6 h-6 flex items-center justify-center rounded-md hover:bg-white/[0.06] text-text-dim hover:text-text-muted",
              menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"
            )}
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>

          {menuOpen && (
            <div
              ref={menuRef}
              className="glass-card absolute right-0 top-full mt-1 w-40 py-1 z-10 border border-border shadow-lg"
            >
              <button
                onClick={() => setMenuOpen(false)}
                className="w-full text-left px-3 py-2 text-[12px] text-text-muted hover:text-text hover:bg-white/[0.04] transition-colors flex items-center gap-2"
              >
                {task.completed ? (
                  <>
                    <Circle className="w-3.5 h-3.5" />
                    Mark incomplete
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Mark complete
                  </>
                )}
              </button>
              <button
                onClick={() => setMenuOpen(false)}
                className="w-full text-left px-3 py-2 text-[12px] text-text-muted hover:text-text hover:bg-white/[0.04] transition-colors flex items-center gap-2"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Open in vault
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
