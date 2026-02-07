"use client";

import { useChatContext } from "@/components/providers/ChatProvider";
import { ChatMessages } from "@/components/chat/ChatMessages";
import { ChatInput } from "@/components/chat/ChatInput";
import { ProviderToggle } from "@/components/chat/ProviderToggle";
import { Plus } from "lucide-react";

export default function ChatPage() {
  const { messages, newConversation } = useChatContext();
  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-col h-full">
      {/* Header bar */}
      <div className="flex items-center justify-between px-6 h-14 shrink-0 border-b border-border">
        <h1 className="text-base font-bold text-text tracking-tight">Chat</h1>
        <div className="flex items-center gap-3">
          <ProviderToggle />
          {hasMessages && (
            <button
              onClick={newConversation}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.07] border border-border text-text-muted hover:text-text text-xs font-semibold transition-all duration-200"
            >
              <Plus className="w-3.5 h-3.5" />
              New
            </button>
          )}
        </div>
      </div>

      {hasMessages ? (
        <>
          <ChatMessages />
          <div className="px-4 pb-4">
            <ChatInput variant="bottom" />
          </div>
        </>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center px-4">
          <ChatInput variant="centered" />
        </div>
      )}
    </div>
  );
}
