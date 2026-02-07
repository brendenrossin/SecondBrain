"use client";

import { cn, daysUntil } from "@/lib/utils";

export function DueBadge({ dueDate }: { dueDate: string }) {
  if (!dueDate) return <span className="text-text-dim text-[10px] font-medium">No date</span>;

  const days = daysUntil(dueDate);

  let label: string;
  let colorClass: string;

  if (days < -1) {
    label = `${Math.abs(days)}d overdue`;
    colorClass = "bg-danger-dim text-danger shadow-[0_0_8px_rgba(248,113,113,0.15)]";
  } else if (days === -1) {
    label = "1d overdue";
    colorClass = "bg-danger-dim text-danger shadow-[0_0_8px_rgba(248,113,113,0.15)]";
  } else if (days === 0) {
    label = "Today";
    colorClass = "bg-danger-dim text-danger shadow-[0_0_8px_rgba(248,113,113,0.15)]";
  } else if (days === 1) {
    label = "Tomorrow";
    colorClass = "bg-warning-dim text-warning shadow-[0_0_8px_rgba(251,191,36,0.12)]";
  } else if (days <= 3) {
    label = `${days}d`;
    colorClass = "bg-warning-dim text-warning shadow-[0_0_8px_rgba(251,191,36,0.12)]";
  } else if (days <= 7) {
    label = `${days}d`;
    colorClass = "bg-accent-glow text-accent";
  } else {
    label = `${days}d`;
    colorClass = "bg-white/[0.04] text-text-muted";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 rounded-lg text-[10px] font-semibold shrink-0",
        colorClass
      )}
    >
      {label}
    </span>
  );
}
