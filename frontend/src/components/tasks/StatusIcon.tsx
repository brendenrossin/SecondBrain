"use client";

import { Circle, CheckCircle2, CircleDot } from "lucide-react";
import { cn } from "@/lib/utils";

type IconSize = "sm" | "md";

const SIZE_CLASS: Record<IconSize, string> = {
  sm: "w-3.5 h-3.5",
  md: "w-[18px] h-[18px]",
};

interface StatusIconProps {
  status: string;
  size?: IconSize;
  className?: string;
}

export function StatusIcon({ status, size = "md", className }: StatusIconProps): React.JSX.Element {
  const sizeClass = SIZE_CLASS[size];

  switch (status) {
    case "done":
      return <CheckCircle2 className={cn(sizeClass, "text-success shrink-0", className)} />;
    case "in_progress":
      return <CircleDot className={cn(sizeClass, "text-accent shrink-0", className)} />;
    default:
      return <Circle className={cn(sizeClass, "text-text-dim shrink-0", className)} />;
  }
}
