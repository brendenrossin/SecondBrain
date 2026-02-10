"use client";

import { useChatContext } from "@/components/providers/ChatProvider";
import { cn } from "@/lib/utils";

export function ProviderToggle() {
  const { provider, setProvider } = useChatContext();

  const buttons = [
    { key: "anthropic" as const, label: "Claude" },
    { key: "local" as const, label: "Local" },
    { key: "openai" as const, label: "OpenAI" },
  ];

  return (
    <div className="flex rounded-xl bg-white/[0.03] border border-border text-xs p-0.5">
      {buttons.map((btn) => (
        <button
          key={btn.key}
          onClick={() => setProvider(btn.key)}
          className={cn(
            "px-3.5 py-1.5 rounded-lg font-semibold transition-all duration-200",
            provider === btn.key
              ? "bg-accent text-white shadow-[0_0_10px_rgba(79,142,247,0.2)]"
              : "text-text-dim hover:text-text-muted"
          )}
        >
          {btn.label}
        </button>
      ))}
    </div>
  );
}
