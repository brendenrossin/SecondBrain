"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowUp, Brain } from "lucide-react";
import { useChatContext } from "@/components/providers/ChatProvider";

interface ChatInputProps {
  variant?: "centered" | "bottom";
}

export function ChatInput({ variant = "bottom" }: ChatInputProps) {
  const { sendMessage, isStreaming } = useChatContext();
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = variant === "centered" ? 200 : 150;
    el.style.height = Math.min(el.scrollHeight, max) + "px";
  }, [variant]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming) return;
    sendMessage(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  if (variant === "centered") {
    return (
      <div className="w-full max-w-2xl">
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-accent/10 flex items-center justify-center mb-5 shadow-[0_0_30px_rgba(79,142,247,0.12)]">
            <Brain className="w-8 h-8 text-accent drop-shadow-[0_0_8px_rgba(79,142,247,0.4)]" />
          </div>
          <h2 className="text-2xl font-bold text-text mb-2 tracking-tight">
            Ask your SecondBrain
          </h2>
          <p className="text-sm text-text-muted">
            Search your notes, get answers with citations
          </p>
        </div>
        <div className="glass-card p-1.5">
          <textarea
            ref={textareaRef}
            data-chat-input
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              adjustHeight();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your vault..."
            rows={3}
            className="w-full resize-none bg-transparent text-sm text-text outline-none placeholder:text-text-dim px-4 py-3 leading-relaxed"
          />
          <div className="flex items-center justify-end px-2 pb-1.5">
            <button
              onClick={handleSubmit}
              disabled={!value.trim() || isStreaming}
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent hover:bg-accent-hover disabled:bg-white/[0.06] disabled:cursor-not-allowed text-white transition-all duration-200 shadow-[0_0_12px_rgba(79,142,247,0.2)] hover:shadow-[0_0_20px_rgba(79,142,247,0.3)]"
            >
              <ArrowUp className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-white/[0.02] px-4 py-3 shadow-[0_2px_12px_rgba(0,0,0,0.2)] focus-within:border-accent/20 focus-within:shadow-[0_0_16px_rgba(79,142,247,0.06)] transition-all duration-200">
        <textarea
          ref={textareaRef}
          data-chat-input
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            adjustHeight();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Ask a follow-up..."
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm text-text outline-none placeholder:text-text-dim leading-relaxed"
        />
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isStreaming}
          className="shrink-0 flex items-center justify-center w-9 h-9 rounded-xl bg-accent hover:bg-accent-hover disabled:bg-white/[0.06] disabled:cursor-not-allowed text-white transition-all duration-200 shadow-[0_0_12px_rgba(79,142,247,0.2)]"
        >
          <ArrowUp className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
