"use client";

import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface TaskFiltersProps {
  showCompleted: boolean;
  onToggleCompleted: () => void;
  search: string;
  onSearchChange: (v: string) => void;
}

export function TaskFilters({
  showCompleted,
  onToggleCompleted,
  search,
  onSearchChange,
}: TaskFiltersProps) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <div className="flex items-center gap-2.5 flex-1 rounded-xl border border-border bg-white/[0.02] px-4 py-2.5 focus-within:border-accent/30 focus-within:shadow-[0_0_12px_rgba(79,142,247,0.08)] transition-all">
        <Search className="w-4 h-4 text-text-dim" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search tasks..."
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-text-dim"
        />
      </div>
      <button
        onClick={onToggleCompleted}
        className={cn(
          "text-xs font-semibold px-4 py-2.5 rounded-xl border transition-all duration-200",
          showCompleted
            ? "bg-accent text-white border-accent shadow-[0_0_16px_rgba(79,142,247,0.2)]"
            : "bg-white/[0.02] border-border text-text-muted hover:text-text hover:bg-white/[0.04]"
        )}
      >
        {showCompleted ? "Hide done" : "Show done"}
      </button>
    </div>
  );
}
