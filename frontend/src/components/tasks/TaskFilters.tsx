"use client";

import { Search, X, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StatFilter } from "./TaskTree";

const FILTER_LABELS: Record<StatFilter, string> = {
  active: "Active",
  overdue: "Overdue",
  dueToday: "Due Today",
  completed: "Completed",
};

interface TaskFiltersProps {
  showCompleted: boolean;
  onToggleCompleted: () => void;
  search: string;
  onSearchChange: (v: string) => void;
  activeFilter: StatFilter | null;
  onClearFilter: () => void;
}

export function TaskFilters({
  showCompleted,
  onToggleCompleted,
  search,
  onSearchChange,
  activeFilter,
  onClearFilter,
}: TaskFiltersProps): React.JSX.Element {
  return (
    <div className="flex flex-col gap-3 mb-5">
      <div className="flex items-center gap-3">
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

      {/* Filter chips row */}
      {activeFilter && (
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={onClearFilter}
            className="flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded-lg border border-accent/30 bg-accent/10 text-accent hover:bg-accent/15 transition-colors"
          >
            {FILTER_LABELS[activeFilter]}
            <X className="w-3 h-3" />
          </button>
          {/* Stub filter chips for future use */}
          {["Status", "Project", "Due date"].map((label) => (
            <button
              key={label}
              disabled
              className="flex items-center gap-1 text-[11px] font-medium px-3 py-1.5 rounded-lg border border-border bg-white/[0.02] text-text-dim cursor-not-allowed"
            >
              {label}
              <ChevronDown className="w-3 h-3" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
