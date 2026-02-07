"use client";

import { Plus } from "lucide-react";
import { useChatContext } from "@/components/providers/ChatProvider";
import { ChatMessages } from "./ChatMessages";
import { ChatInput } from "./ChatInput";
import { ProviderToggle } from "./ProviderToggle";

export function ChatPanel() {
  const { newConversation } = useChatContext();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 h-14 border-b border-border shrink-0">
        <span className="text-sm font-medium">Chat</span>
        <div className="flex items-center gap-2">
          <ProviderToggle />
          <button
            onClick={newConversation}
            className="p-1.5 rounded-md hover:bg-surface-hover text-text-muted hover:text-text transition-colors"
            title="New conversation"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      <ChatMessages />
      <ChatInput />
    </div>
  );
}
