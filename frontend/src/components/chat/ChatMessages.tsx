"use client";

import { useEffect, useRef } from "react";
import { useChatContext } from "@/components/providers/ChatProvider";
import { ChatMessage } from "./ChatMessage";

export function ChatMessages() {
  const { messages, isStreaming, wikiSuggestion, conversationId, lastQuery } = useChatContext();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-5 py-5">
      <div className="max-w-3xl mx-auto flex flex-col gap-5">
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            message={msg}
            isStreaming={
              isStreaming && i === messages.length - 1 && msg.role === "assistant"
            }
            isLastAssistant={msg.role === "assistant" && i === messages.length - 1}
            wikiSuggestion={wikiSuggestion}
            conversationId={conversationId}
            query={lastQuery}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
