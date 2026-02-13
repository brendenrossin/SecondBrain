"use client";

import { CalendarDays, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface DayButtonProps {
  date: Date;
  eventCount: number;
  taskCount: number;
  hasOverdue: boolean;
  hasDueSoon: boolean;
  isSelected: boolean;
  isToday: boolean;
  onClick: () => void;
}

export function DayButton({
  date,
  eventCount,
  taskCount,
  hasOverdue,
  hasDueSoon,
  isSelected,
  isToday,
  onClick,
}: DayButtonProps): React.JSX.Element {
  const dayAbbr = date.toLocaleDateString("en-US", { weekday: "short" });
  const dateNum = date.getDate();

  const taskColor = hasOverdue
    ? "text-rose-400"
    : hasDueSoon
      ? "text-amber-400"
      : "text-text-dim";

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex-1 flex flex-col items-center py-2 min-h-[64px] transition-colors",
        isSelected
          ? "border-b-2 border-accent bg-white/[0.04]"
          : "border-b-2 border-transparent"
      )}
    >
      {/* Today indicator */}
      {isToday ? (
        <span className="w-1.5 h-1.5 rounded-full bg-accent mb-0.5" />
      ) : (
        <span className="w-1.5 h-1.5 mb-0.5" />
      )}

      <span className="text-[10px] text-text-dim uppercase font-medium">{dayAbbr}</span>
      <span
        className={cn(
          "text-sm font-medium",
          isToday ? "text-accent" : "text-text"
        )}
      >
        {dateNum}
      </span>

      {/* Badges — hidden when selected */}
      {!isSelected && (
        <div className="flex items-center gap-1.5 mt-0.5">
          {eventCount > 0 && (
            <span className="flex items-center gap-0.5 text-emerald-400">
              <CalendarDays className="w-2.5 h-2.5" />
              <span className="text-[9px] font-medium">{eventCount}</span>
            </span>
          )}
          {taskCount > 0 && (
            <span className={cn("flex items-center gap-0.5", taskColor)}>
              <CheckCircle2 className="w-2.5 h-2.5" />
              <span className="text-[9px] font-medium">{taskCount}</span>
            </span>
          )}
        </div>
      )}
    </button>
  );
}
