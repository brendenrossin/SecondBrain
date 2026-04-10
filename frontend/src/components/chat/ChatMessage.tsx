"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot, BookmarkPlus, Loader2, Check } from "lucide-react";
import type { ConversationMessage, WikiSuggestion } from "@/lib/types";
import { wikiSaveAnswer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CitationsList } from "./CitationsList";
import { StreamingIndicator } from "./StreamingIndicator";

interface ChatMessageProps {
  message: ConversationMessage;
  isStreaming?: boolean;
  isLastAssistant?: boolean;
  wikiSuggestion?: WikiSuggestion | null;
  conversationId?: string | null;
  query?: string;
}

type SaveStatus = "idle" | "saving" | "saved" | "error";

function AssistantContent({
  content,
  isStreaming,
}: {
  content: string;
  isStreaming?: boolean;
}) {
  if (content) {
    return (
      <div className="markdown-content text-[13px]">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }
  if (isStreaming) {
    return <StreamingIndicator />;
  }
  return null;
}

export function ChatMessage({
  message,
  isStreaming,
  isLastAssistant,
  wikiSuggestion,
  conversationId,
  query,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  const showWikiChip =
    !isUser &&
    isLastAssistant &&
    !isStreaming &&
    wikiSuggestion?.eligible === true &&
    !!conversationId &&
    !!query;

  async function handleSaveAsWiki() {
    if (saveStatus !== "idle" || !conversationId || !query) return;
    setSaveStatus("saving");
    try {
      await wikiSaveAnswer({
        conversation_id: conversationId,
        answer_text: message.content,
        query,
        citations: [...new Set(message.citations?.map((c) => c.note_title) ?? [])],
      });
      setSaveStatus("saved");
    } catch {
      setSaveStatus("error");
    }
  }

  const wikiIcon =
    saveStatus === "saving" ? (
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
    ) : saveStatus === "saved" ? (
      <Check className="w-3.5 h-3.5" />
    ) : (
      <BookmarkPlus className="w-3.5 h-3.5" />
    );

  const wikiLabel =
    saveStatus === "saving"
      ? "Saving…"
      : saveStatus === "saved"
      ? "Saved to wiki"
      : saveStatus === "error"
      ? "Save failed"
      : "Save as wiki page";

  return (
    <div className="flex gap-3">
      <div
        className={cn(
          "shrink-0 w-8 h-8 rounded-xl flex items-center justify-center mt-1",
          isUser
            ? "bg-accent/12 text-accent shadow-[0_0_10px_rgba(79,142,247,0.1)]"
            : "bg-success-dim text-success shadow-[0_0_10px_rgba(52,211,153,0.1)]"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] font-semibold text-text-dim mb-1.5 uppercase tracking-wider">
          {isUser ? "You" : "SecondBrain"}
        </div>
        <div
          className={cn(
            "rounded-2xl px-6 py-5",
            isUser
              ? "glass-card"
              : "bg-surface border border-border shadow-[0_2px_8px_rgba(0,0,0,0.2)]"
          )}
        >
          {isUser ? (
            <p className="text-[13px] leading-relaxed break-words">{message.content}</p>
          ) : (
            <AssistantContent content={message.content} isStreaming={isStreaming} />
          )}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 ml-1">
            <CitationsList citations={message.citations} />
          </div>
        )}
        {showWikiChip && (
          <button
            onClick={handleSaveAsWiki}
            disabled={saveStatus !== "idle"}
            className={cn(
              "mt-2 ml-1 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200",
              saveStatus === "saved"
                ? "bg-success/10 text-success"
                : saveStatus === "error"
                ? "bg-red-500/10 text-red-400"
                : "bg-accent/10 text-accent hover:bg-accent/20 cursor-pointer"
            )}
          >
            {wikiIcon}
            {wikiLabel}
          </button>
        )}
      </div>
    </div>
  );
}
