"use client";

import { useEffect, useRef } from "react";
import { useChatContext } from "@/components/providers/ChatProvider";
import { ChatMessage } from "./ChatMessage";

export function ChatMessages() {
  const { messages, isStreaming } = useChatContext();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            message={msg}
            isStreaming={
              isStreaming && i === messages.length - 1 && msg.role === "assistant"
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
