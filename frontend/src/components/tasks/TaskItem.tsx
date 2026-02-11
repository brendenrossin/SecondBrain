"use client";

import { useEffect, useRef, useState } from "react";
import { Circle, CheckCircle2, MoreHorizontal, ExternalLink, CircleDot } from "lucide-react";
import type { TaskResponse } from "@/lib/types";
import { updateTask } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DueBadge } from "./DueBadge";
import { StatusIcon } from "./StatusIcon";

interface TaskItemProps {
  task: TaskResponse;
  onUpdate?: () => void;
  onSelect?: (task: TaskResponse) => void;
}

export function TaskItem({ task, onUpdate, onSelect }: TaskItemProps): React.JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
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

  async function handleStatusChange(newStatus: "open" | "in_progress" | "done") {
    if (updating) return;
    setUpdating(true);
    try {
      await updateTask({
        text: task.text,
        category: task.category,
        sub_project: task.sub_project,
        status: newStatus,
      });
      onUpdate?.();
    } catch {
      // silently fail — the UI will remain in its current state
    } finally {
      setUpdating(false);
    }
  }

  function handleCheckboxClick(e: React.MouseEvent) {
    e.stopPropagation();
    handleStatusChange(task.status === "done" ? "open" : "done");
  }

  return (
    <div
      onClick={() => onSelect?.(task)}
      className={cn(
        "flex items-center gap-3.5 px-5 py-3.5 mx-2 rounded-xl",
        "hover:bg-white/[0.03] transition-all duration-150",
        "group",
        onSelect && "cursor-pointer",
        updating && "opacity-60 pointer-events-none"
      )}
    >
      <button
        onClick={handleCheckboxClick}
        className="shrink-0 focus-ring rounded-full"
        aria-label={task.status === "done" ? "Mark incomplete" : "Mark complete"}
      >
        <StatusIcon status={task.status} className="group-hover:text-text-muted transition-colors" />
      </button>

      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "text-[13px] leading-snug font-medium truncate",
            task.status === "done" ? "text-text-dim line-through" : "text-text"
          )}
        >
          {task.text}
        </p>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {task.status !== "done" && task.days_open > 0 && (
          <span className="text-[10px] text-text-dim font-medium tabular-nums">
            {task.days_open}d open
          </span>
        )}
        <DueBadge dueDate={task.due_date} />

        <div className="relative">
          <button
            ref={buttonRef}
            aria-label="Task options"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((v) => !v);
            }}
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
              className="glass-card absolute right-0 top-full mt-1 w-44 py-1 z-10 border border-border shadow-lg"
            >
              {task.status !== "done" && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(false);
                    handleStatusChange("done");
                  }}
                  className="w-full text-left px-3 py-2 text-[12px] text-text-muted hover:text-text hover:bg-white/[0.04] transition-colors flex items-center gap-2"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Mark complete
                </button>
              )}
              {task.status === "done" && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(false);
                    handleStatusChange("open");
                  }}
                  className="w-full text-left px-3 py-2 text-[12px] text-text-muted hover:text-text hover:bg-white/[0.04] transition-colors flex items-center gap-2"
                >
                  <Circle className="w-3.5 h-3.5" />
                  Mark incomplete
                </button>
              )}
              {task.status !== "in_progress" && task.status !== "done" && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuOpen(false);
                    handleStatusChange("in_progress");
                  }}
                  className="w-full text-left px-3 py-2 text-[12px] text-text-muted hover:text-text hover:bg-white/[0.04] transition-colors flex items-center gap-2"
                >
                  <CircleDot className="w-3.5 h-3.5" />
                  Mark in progress
                </button>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setMenuOpen(false);
                }}
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
