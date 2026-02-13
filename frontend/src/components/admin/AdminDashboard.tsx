"use client";

import { useEffect, useState, useCallback } from "react";
import {
  DollarSign,
  Zap,
  MessageSquare,
  Database,
  RefreshCw,
  Clock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getCostSummary,
  getDailyCosts,
  getAdminStats,
  getSyncStatus,
} from "@/lib/api";
import type { SyncStatusResponse } from "@/lib/api";
import type {
  CostSummaryResponse,
  DailyCost,
  DailyCostsResponse,
  AdminStatsResponse,
} from "@/lib/types";

type Period = "week" | "month" | "all";

const PERIOD_LABELS: Record<Period, string> = {
  week: "Week",
  month: "Month",
  all: "All Time",
};

const CHART_DAYS: Record<Period, number> = {
  week: 7,
  month: 30,
  all: 365,
};

const CHART_TITLES: Record<Period, string> = {
  week: "Daily Cost (This Week)",
  month: "Daily Cost (Last 30 Days)",
  all: "Weekly Cost (All Time)",
};

function formatCost(cents: number): string {
  if (cents < 0.01) return "$0.00";
  return `$${cents.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/* ── Stat card ── */
function StatCard({
  icon: Icon,
  label,
  value,
  subValue,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  subValue?: string;
  color: string;
}) {
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

/* ── Provider breakdown row ── */
function ProviderRow({
  name,
  cost,
  calls,
  inputTokens,
  outputTokens,
}: {
  name: string;
  cost: number;
  calls: number;
  inputTokens: number;
  outputTokens: number;
}) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-b-0">
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-accent" />
        <span className="text-sm font-medium text-text capitalize">{name}</span>
      </div>
      <div className="flex items-center gap-6 text-xs text-text-muted tabular-nums">
        <span>{calls} calls</span>
        <span>{formatTokens(inputTokens)} in</span>
        <span>{formatTokens(outputTokens)} out</span>
        <span className="font-semibold text-text min-w-[60px] text-right">
          {formatCost(cost)}
        </span>
      </div>
    </div>
  );
}

/* ── Usage type breakdown row ── */
function UsageTypeRow({
  name,
  cost,
  calls,
}: {
  name: string;
  cost: number;
  calls: number;
}) {
  const labels: Record<string, string> = {
    chat_rerank: "Reranking",
    chat_answer: "Answers",
    inbox: "Inbox Processing",
  };
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-b-0">
      <span className="text-sm font-medium text-text">
        {labels[name] || name}
      </span>
      <div className="flex items-center gap-6 text-xs text-text-muted tabular-nums">
        <span>{calls} calls</span>
        <span className="font-semibold text-text min-w-[60px] text-right">
          {formatCost(cost)}
        </span>
      </div>
    </div>
  );
}

/* ── Cost bar chart (CSS-only) ── */
const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "bg-accent",
  openai: "bg-success",
  ollama: "bg-text-dim",
};

type ChartBar = {
  key: string;
  label: string;
  sublabel: string;
  cost_usd: number;
  calls: number;
  by_provider: Record<string, number>;
};

const SHORT_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatShortDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return `${SHORT_MONTHS[d.getMonth()]} ${d.getDate()}`;
}

function toDateKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function buildDailyBars(
  byDate: Map<string, DailyCost>,
  numDays: number,
  labelFn: (date: Date, daysAgo: number, dateKey: string) => string
): ChartBar[] {
  const today = new Date();
  const bars: ChartBar[] = [];
  for (let i = numDays - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = toDateKey(d);
    const day = byDate.get(key);
    bars.push({
      key,
      label: labelFn(d, i, key),
      sublabel: formatShortDate(key),
      cost_usd: day?.cost_usd ?? 0,
      calls: day?.calls ?? 0,
      by_provider: day?.by_provider ?? {},
    });
  }
  return bars;
}

function buildWeeklyBuckets(daily: DailyCost[]): ChartBar[] {
  if (daily.length === 0) return [];

  const weekMap = new Map<string, ChartBar>();
  for (const day of daily) {
    const d = new Date(day.date + "T00:00:00");
    const dayOfWeek = d.getDay();
    const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;
    const monday = new Date(d);
    monday.setDate(d.getDate() + mondayOffset);
    const weekKey = toDateKey(monday);

    const existing = weekMap.get(weekKey);
    if (existing) {
      existing.cost_usd += day.cost_usd;
      existing.calls += day.calls;
      for (const [prov, cost] of Object.entries(day.by_provider)) {
        existing.by_provider[prov] = (existing.by_provider[prov] || 0) + cost;
      }
    } else {
      weekMap.set(weekKey, {
        key: weekKey,
        label: formatShortDate(weekKey),
        sublabel: `Week of ${formatShortDate(weekKey)}`,
        cost_usd: day.cost_usd,
        calls: day.calls,
        by_provider: { ...day.by_provider },
      });
    }
  }
  return Array.from(weekMap.values());
}

function buildChartBars(data: DailyCostsResponse, period: Period): ChartBar[] {
  const byDate = new Map(data.daily.map((d) => [d.date, d]));

  if (period === "week") {
    return buildDailyBars(byDate, 7, (d) => SHORT_DAYS[d.getDay()]);
  }
  if (period === "month") {
    return buildDailyBars(
      byDate,
      30,
      (_d, daysAgo, key) => (daysAgo % 7 === 0 ? formatShortDate(key) : "")
    );
  }
  return buildWeeklyBuckets(data.daily);
}

/** Round up to a nice ceiling for the Y-axis (e.g., 0.07 → 0.10, 0.23 → 0.25, 1.7 → 2.00). */
function niceMax(value: number): number {
  if (value <= 0) return 0.10;
  const steps = [0.05, 0.10, 0.25, 0.50, 1.00, 2.50, 5.00, 10.00, 25.00, 50.00, 100.00];
  for (const step of steps) {
    const ceil = Math.ceil(value / step) * step;
    if (ceil >= value) return ceil;
  }
  return Math.ceil(value / 100) * 100;
}

function formatYLabel(value: number): string {
  if (value >= 10) return `$${value.toFixed(0)}`;
  if (value >= 1) return `$${value.toFixed(1)}`;
  return `$${value.toFixed(2)}`;
}

function CostChart({ bars }: { bars: ChartBar[] }) {
  if (bars.length === 0) {
    return (
      <p className="text-sm text-text-dim py-6 text-center">
        No usage data yet
      </p>
    );
  }

  const rawMax = Math.max(...bars.map((b) => b.cost_usd));
  const ceiling = niceMax(rawMax);
  const hasLabels = bars.some((b) => b.label);

  return (
    <div>
      <div className="flex h-48">
        {/* Y-axis */}
        <div className="flex flex-col justify-between pr-2 py-0 shrink-0 w-10">
          <span className="text-[10px] text-text-dim tabular-nums text-right leading-none">
            {formatYLabel(ceiling)}
          </span>
          <span className="text-[10px] text-text-dim tabular-nums text-right leading-none">
            {formatYLabel(ceiling / 2)}
          </span>
          <span className="text-[10px] text-text-dim tabular-nums text-right leading-none">
            $0
          </span>
        </div>
        {/* Bars area */}
        <div className="flex-1 flex gap-1 relative">
          {/* Grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
            <div className="border-b border-border/40" />
            <div className="border-b border-border/40" />
            <div className="border-b border-border/40" />
          </div>
          {bars.map((bar) => {
            const pct = ceiling > 0 ? (bar.cost_usd / ceiling) * 100 : 0;
            const providers = Object.entries(bar.by_provider);
            return (
              <div
                key={bar.key}
                className="flex-1 flex flex-col justify-end min-w-0 group relative z-10"
              >
                {/* Tooltip */}
                <div className="absolute bottom-full mb-2 hidden group-hover:block z-20 bg-card border border-border rounded-lg px-3 py-2 text-xs shadow-lg whitespace-nowrap pointer-events-none">
                  <p className="font-medium text-text">{bar.sublabel}</p>
                  <p className="text-text-muted">
                    {formatCost(bar.cost_usd)} / {bar.calls} calls
                  </p>
                </div>
                {/* Bar */}
                <div
                  className="w-full rounded-t-sm overflow-hidden flex flex-col-reverse"
                  style={{ height: `${Math.max(pct, bar.cost_usd > 0 ? 3 : 0)}%` }}
                >
                  {providers.map(([provider, providerCost]) => {
                    const segPct =
                      bar.cost_usd > 0 ? (providerCost / bar.cost_usd) * 100 : 0;
                    return (
                      <div
                        key={provider}
                        className={cn(
                          "w-full transition-all",
                          PROVIDER_COLORS[provider] || "bg-text-dim"
                        )}
                        style={{ height: `${segPct}%`, minHeight: segPct > 0 ? "2px" : "0" }}
                      />
                    );
                  })}
                </div>
                {/* Zero-data indicator */}
                {bar.cost_usd === 0 && (
                  <div className="w-full h-[1px] bg-border/50 rounded" />
                )}
              </div>
            );
          })}
        </div>
      </div>
      {/* X-axis labels */}
      {hasLabels && (
        <div className="flex gap-1 mt-2 ml-10">
          {bars.map((bar) => (
            <div key={bar.key} className="flex-1 min-w-0 text-center">
              <span className="text-[10px] text-text-dim truncate block">
                {bar.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Main dashboard ── */
export function AdminDashboard() {
  const [period, setPeriod] = useState<Period>("week");
  const [costs, setCosts] = useState<CostSummaryResponse | null>(null);
  const [dailyCosts, setDailyCosts] = useState<DailyCostsResponse | null>(null);
  const [stats, setStats] = useState<AdminStatsResponse | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const chartDays = CHART_DAYS[period];
      const [c, d, s, ss] = await Promise.all([
        getCostSummary(period),
        getDailyCosts(chartDays),
        getAdminStats(),
        getSyncStatus(),
      ]);
      setCosts(c);
      setDailyCosts(d);
      setStats(s);
      setSyncStatus(ss);
    } catch (err) {
      console.error("Failed to load admin data:", err);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      {/* Header row: period selector + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-card border border-border">
          {(["week", "month", "all"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                period === p
                  ? "bg-accent/15 text-accent"
                  : "text-text-muted hover:text-text hover:bg-white/5"
              )}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="p-2 rounded-lg text-text-dim hover:text-text hover:bg-white/5 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {/* Sync status indicator */}
      {syncStatus && (
        <div className="glass-card p-4 flex items-center gap-3">
          <div
            className={cn(
              "w-2.5 h-2.5 rounded-full shrink-0",
              syncStatus.status === "ok" && "bg-success",
              syncStatus.status === "stale" && "bg-warning",
              syncStatus.status === "failed" && "bg-red-500",
              syncStatus.status === "unknown" && "bg-text-dim"
            )}
          />
          <div className="text-sm">
            <span className="text-text font-medium">Last sync: </span>
            <span className="text-text-muted">
              {syncStatus.hours_ago != null
                ? syncStatus.hours_ago < 1
                  ? "< 1 hour ago"
                  : `${Math.round(syncStatus.hours_ago)}h ago`
                : "Never"}
            </span>
            {syncStatus.status === "failed" && syncStatus.error && (
              <span className="text-red-400 ml-2 text-xs">
                Failed: {syncStatus.error.slice(0, 80)}
              </span>
            )}
            {syncStatus.status === "stale" && (
              <span className="text-warning ml-2 text-xs">Stale (&gt; 25h)</span>
            )}
          </div>
        </div>
      )}

      {/* Row 1: Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={DollarSign}
          label={`Cost (${PERIOD_LABELS[period]})`}
          value={costs ? formatCost(costs.total_cost) : "--"}
          subValue={costs ? `${costs.total_calls} API calls` : undefined}
          color="bg-accent/15 text-accent"
        />
        <StatCard
          icon={Zap}
          label="LLM Calls (Total)"
          value={stats ? String(stats.total_llm_calls) : "--"}
          subValue={stats ? `${formatCost(stats.total_llm_cost)} total spend` : undefined}
          color="bg-warning/15 text-warning"
        />
        <StatCard
          icon={MessageSquare}
          label="Chat Queries"
          value={stats ? String(stats.total_queries) : "--"}
          subValue={
            stats
              ? `${stats.avg_latency_ms.toFixed(0)}ms avg latency`
              : undefined
          }
          color="bg-success/15 text-success"
        />
        <StatCard
          icon={Database}
          label="Indexed Files"
          value={stats ? String(stats.index_file_count) : "--"}
          subValue={
            stats ? `${stats.total_conversations} conversations` : undefined
          }
          color="bg-purple/15 text-purple"
        />
      </div>

      {/* Row 2: Provider breakdown */}
      {costs && Object.keys(costs.by_provider).length > 0 && (
        <div className="glass-card p-5">
          <h3 className="text-sm font-bold text-text mb-3 flex items-center gap-2">
            <Clock className="w-4 h-4 text-text-dim" />
            Cost by Provider
          </h3>
          {Object.entries(costs.by_provider).map(([provider, data]) => (
            <ProviderRow
              key={provider}
              name={provider}
              cost={data.cost}
              calls={data.calls}
              inputTokens={data.input_tokens}
              outputTokens={data.output_tokens}
            />
          ))}
        </div>
      )}

      {/* Row 3: Usage type breakdown */}
      {costs && Object.keys(costs.by_usage_type).length > 0 && (
        <div className="glass-card p-5">
          <h3 className="text-sm font-bold text-text mb-3">Cost by Usage Type</h3>
          {Object.entries(costs.by_usage_type).map(([type, data]) => (
            <UsageTypeRow key={type} name={type} cost={data.cost} calls={data.calls} />
          ))}
        </div>
      )}

      {/* Row 4: Cost chart */}
      {dailyCosts && (
        <div className="glass-card p-5">
          <h3 className="text-sm font-bold text-text mb-4">
            {CHART_TITLES[period]}
          </h3>
          <CostChart bars={buildChartBars(dailyCosts, period)} />
          {/* Legend */}
          <div className="flex gap-4 mt-3 text-xs text-text-dim">
            {Object.entries(PROVIDER_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-1.5">
                <div className={cn("w-2.5 h-2.5 rounded-sm", color)} />
                <span className="capitalize">{name}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
