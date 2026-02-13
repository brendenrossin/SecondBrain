import { cn } from "@/lib/utils";

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  subValue?: string;
  color: string;
}

export function StatCard({
  icon: Icon,
  label,
  value,
  subValue,
  color,
}: StatCardProps): React.ReactElement {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center gap-3 mb-3">
        <div
          className={cn(
            "w-9 h-9 rounded-xl flex items-center justify-center",
            color
          )}
        >
          <Icon className="w-4.5 h-4.5 text-current" />
        </div>
        <span className="text-xs text-text-dim font-medium uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className="text-2xl font-bold text-text tabular-nums">{value}</p>
      {subValue && (
        <p className="text-xs text-text-dim mt-1">{subValue}</p>
      )}
    </div>
  );
}
