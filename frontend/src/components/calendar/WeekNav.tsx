"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn, formatDateRange } from "@/lib/utils";

interface WeekNavProps {
  weekStart: Date;
  weekEnd: Date;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  showWeekend?: boolean;
  onToggleWeekend?: (show: boolean) => void;
}

export function WeekNav({
  weekStart,
  weekEnd,
  onPrev,
  onNext,
  onToday,
  showWeekend,
  onToggleWeekend,
}: WeekNavProps): React.JSX.Element {
  return (
    <div className="flex items-center gap-2 mb-5">
      <button
        onClick={onPrev}
        className="p-2 rounded-xl border border-border bg-white/[0.02] hover:bg-white/[0.05] text-text-muted hover:text-text transition-all duration-200"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <span className="text-sm font-bold min-w-[200px] text-center text-text tracking-tight">
        {formatDateRange(weekStart, weekEnd)}
      </span>
      <button
        onClick={onNext}
        className="p-2 rounded-xl border border-border bg-white/[0.02] hover:bg-white/[0.05] text-text-muted hover:text-text transition-all duration-200"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
      <button
        onClick={onToday}
        className="ml-2 text-xs font-semibold text-accent hover:text-accent-hover px-4 py-2 rounded-xl border border-accent/20 bg-accent/8 hover:bg-accent/15 shadow-[0_0_12px_rgba(79,142,247,0.08)] transition-all duration-200"
      >
        Today
      </button>

      {/* 5d/7d toggle — desktop only */}
      {onToggleWeekend !== undefined && showWeekend !== undefined && (
        <div className="hidden md:flex ml-2 rounded-xl border border-border overflow-hidden">
          <button
            onClick={() => onToggleWeekend(false)}
            className={cn(
              "px-3 py-1.5 text-[11px] font-semibold transition-colors",
              !showWeekend
                ? "bg-accent/15 text-accent"
                : "text-text-dim hover:text-text-muted hover:bg-white/[0.03]"
            )}
          >
            5d
          </button>
          <button
            onClick={() => onToggleWeekend(true)}
            className={cn(
              "px-3 py-1.5 text-[11px] font-semibold transition-colors border-l border-border",
              showWeekend
                ? "bg-accent/15 text-accent"
                : "text-text-dim hover:text-text-muted hover:bg-white/[0.03]"
            )}
          >
            7d
          </button>
        </div>
      )}
    </div>
  );
}
