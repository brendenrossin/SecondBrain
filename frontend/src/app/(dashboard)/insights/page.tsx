"use client";

import { Lightbulb } from "lucide-react";

export default function InsightsPage() {
  return (
    <div className="h-full">
      <div className="flex items-center px-6 h-14 border-b border-border shrink-0">
        <h1 className="text-base font-bold text-text tracking-tight">Insights</h1>
      </div>
      <div className="flex flex-col items-center justify-center flex-1 px-8 text-center" style={{ height: "calc(100% - 3.5rem)" }}>
        <div className="w-20 h-20 rounded-2xl bg-accent/8 flex items-center justify-center mb-5 shadow-[0_0_40px_rgba(79,142,247,0.1)]">
          <Lightbulb className="w-10 h-10 text-accent drop-shadow-[0_0_10px_rgba(79,142,247,0.4)]" />
        </div>
        <h3 className="text-lg font-bold text-text mb-2 tracking-tight">Coming soon</h3>
        <p className="text-sm text-text-muted max-w-[320px] leading-relaxed">
          Insights will surface metadata, entity extraction, and knowledge graph
          connections from your vault.
        </p>
      </div>
    </div>
  );
}
