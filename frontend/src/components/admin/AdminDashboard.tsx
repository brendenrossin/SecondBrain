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
import { getCostSummary, getDailyCosts, getAdminStats } from "@/lib/api";
import type {
  CostSummaryResponse,
  DailyCostsResponse,
  AdminStatsResponse,
} from "@/lib/types";

type Period = "week" | "month" | "all";

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

/* ── Daily cost bar chart (CSS-only) ── */
const PROVIDER_COLORS: Record<string, string> = {
  anthropic: "bg-accent",
  openai: "bg-success",
  ollama: "bg-text-dim",
};

function DailyCostChart({ data }: { data: DailyCostsResponse }) {
  const { daily } = data;
  if (daily.length === 0) {
    return (
      <p className="text-sm text-text-dim py-6 text-center">
        No usage data yet
      </p>
    );
  }

  const maxCost = Math.max(...daily.map((d) => d.cost_usd), 0.001);

  return (
    <div className="flex items-end gap-1 h-40">
      {daily.map((day) => {
        const pct = (day.cost_usd / maxCost) * 100;
        const providers = Object.entries(day.by_provider);
        return (
          <div
            key={day.date}
            className="flex-1 flex flex-col items-center gap-1 min-w-0 group relative"
          >
            {/* Tooltip */}
            <div className="absolute bottom-full mb-2 hidden group-hover:block z-10 bg-card border border-border rounded-lg px-3 py-2 text-xs shadow-lg whitespace-nowrap">
              <p className="font-medium text-text">{day.date}</p>
              <p className="text-text-muted">
                {formatCost(day.cost_usd)} / {day.calls} calls
              </p>
            </div>
            {/* Bar */}
            <div
              className="w-full rounded-t-sm overflow-hidden flex flex-col-reverse"
              style={{ height: `${Math.max(pct, 2)}%` }}
            >
              {providers.map(([provider, providerCost]) => {
                const segPct =
                  day.cost_usd > 0 ? (providerCost / day.cost_usd) * 100 : 0;
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
          </div>
        );
      })}
    </div>
  );
}

/* ── Main dashboard ── */
export function AdminDashboard() {
  const [period, setPeriod] = useState<Period>("week");
  const [costs, setCosts] = useState<CostSummaryResponse | null>(null);
  const [dailyCosts, setDailyCosts] = useState<DailyCostsResponse | null>(null);
  const [stats, setStats] = useState<AdminStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [c, d, s] = await Promise.all([
        getCostSummary(period),
        getDailyCosts(30),
        getAdminStats(),
      ]);
      setCosts(c);
      setDailyCosts(d);
      setStats(s);
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
              {p === "week" ? "Week" : p === "month" ? "Month" : "All Time"}
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

      {/* Row 1: Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={DollarSign}
          label={`Cost (${period === "all" ? "All Time" : period})`}
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

      {/* Row 4: Daily cost chart */}
      {dailyCosts && (
        <div className="glass-card p-5">
          <h3 className="text-sm font-bold text-text mb-4">
            Daily Cost (Last 30 Days)
          </h3>
          <DailyCostChart data={dailyCosts} />
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
