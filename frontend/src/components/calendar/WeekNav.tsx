"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { formatDateRange } from "@/lib/utils";

interface WeekNavProps {
  weekStart: Date;
  weekEnd: Date;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}

export function WeekNav({
  weekStart,
  weekEnd,
  onPrev,
  onNext,
  onToday,
}: WeekNavProps) {
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
    </div>
  );
}
