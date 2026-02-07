"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { User, Bot } from "lucide-react";
import type { ConversationMessage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { CitationsList } from "./CitationsList";
import { StreamingIndicator } from "./StreamingIndicator";

interface ChatMessageProps {
  message: ConversationMessage;
  isStreaming?: boolean;
}

function normalizeContent(text: string): string {
  // Fix common streaming artifacts: extra spaces before punctuation,
  // double spaces, spaces around hyphens in compound words
  return text
    .replace(/ +,/g, ",")
    .replace(/ +\./g, ".")
    .replace(/ +:/g, ":")
    .replace(/ +;/g, ";")
    .replace(/ {2,}/g, " ")
    .replace(/ -/g, "-")
    .replace(/- /g, "-")
    .replace(/\n{3,}/g, "\n\n");
}

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
          {normalizeContent(content)}
        </ReactMarkdown>
      </div>
    );
  }
  if (isStreaming) {
    return <StreamingIndicator />;
  }
  return null;
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";

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
            "rounded-2xl px-5 py-4",
            isUser
              ? "glass-card"
              : "bg-white/[0.02] border border-border shadow-[0_2px_8px_rgba(0,0,0,0.12)]"
          )}
        >
          {isUser ? (
            <p className="text-[13px] leading-relaxed">{message.content}</p>
          ) : (
            <AssistantContent content={message.content} isStreaming={isStreaming} />
          )}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 ml-1">
            <CitationsList citations={message.citations} />
          </div>
        )}
      </div>
    </div>
  );
}
