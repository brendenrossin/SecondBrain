"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Check, AlertCircle } from "lucide-react";
import { captureText } from "@/lib/api";

type Status = "idle" | "sending" | "success" | "error";

export function CaptureForm(): React.JSX.Element {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resetTimerRef = useRef<ReturnType<typeof setTimeout>>(null);

  // Clean up the success-reset timer on unmount
  useEffect(() => {
    return () => {
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
    };
  }, []);

  async function handleSubmit(): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || status === "sending") return;

    setStatus("sending");
    setMessage("");

    try {
      const res = await captureText(trimmed);
      setStatus("success");
      setMessage(res.message);
      setText("");
      // Reset to idle after 3 seconds so user can capture again
      resetTimerRef.current = setTimeout(() => {
        setStatus("idle");
        setMessage("");
        textareaRef.current?.focus();
      }, 3000);
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Failed to capture");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent): void {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="glass-card p-6">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What's on your mind? Capture a thought, task, or note..."
          className="w-full h-40 bg-transparent text-text placeholder:text-text-dim text-sm leading-relaxed resize-none focus:outline-none"
          disabled={status === "sending"}
          autoFocus
        />

        <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
          <span className="text-xs text-text-dim">
            {text.length > 0 ? `${text.length.toLocaleString()} chars` : ""}
            {text.length > 0 && (
              <span className="ml-3 opacity-60">
                {/Mac|iPhone|iPad/.test(navigator.userAgent) ? "\u2318" : "Ctrl"}
                +Enter to send
              </span>
            )}
          </span>

          <button
            onClick={handleSubmit}
            disabled={!text.trim() || status === "sending"}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
            {status === "sending" ? "Sending..." : "Capture"}
          </button>
        </div>
      </div>

      {/* Status feedback */}
      {message && (
        <div
          className={`mt-4 flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
            status === "success"
              ? "bg-success/10 text-success"
              : "bg-red-500/10 text-red-400"
          }`}
        >
          {status === "success" ? (
            <Check className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          {message}
        </div>
      )}

      <p className="mt-6 text-xs text-text-dim text-center leading-relaxed">
        Captured text is saved to your Inbox and processed on the next sync.
        <br />
        The inbox processor will classify it, extract tasks, and route it to the
        right folder.
      </p>
    </div>
  );
}
