"use client";

import { Lightbulb } from "lucide-react";
import { InsightsDashboard } from "@/components/insights/InsightsDashboard";

export default function InsightsPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Lightbulb className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">
          Insights
        </h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <InsightsDashboard />
      </div>
    </div>
  );
}
