"use client";

import { useChatContext } from "@/components/providers/ChatProvider";
import { cn } from "@/lib/utils";

export function ProviderToggle() {
  const { provider, setProvider } = useChatContext();

  return (
    <div className="flex rounded-xl bg-white/[0.03] border border-border text-xs p-0.5">
      <button
        onClick={() => setProvider("openai")}
        className={cn(
          "px-3.5 py-1.5 rounded-lg font-semibold transition-all duration-200",
          provider === "openai"
            ? "bg-accent text-white shadow-[0_0_10px_rgba(79,142,247,0.2)]"
            : "text-text-dim hover:text-text-muted"
        )}
      >
        OpenAI
      </button>
      <button
        onClick={() => setProvider("local")}
        className={cn(
          "px-3.5 py-1.5 rounded-lg font-semibold transition-all duration-200",
          provider === "local"
            ? "bg-accent text-white shadow-[0_0_10px_rgba(79,142,247,0.2)]"
            : "text-text-dim hover:text-text-muted"
        )}
      >
        Local
      </button>
    </div>
  );
}
