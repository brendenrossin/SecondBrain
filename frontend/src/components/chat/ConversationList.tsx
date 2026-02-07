"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { useChatContext } from "@/components/providers/ChatProvider";
import { getConversations, getConversation, deleteConversation } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { ConversationSummary } from "@/lib/types";

export function ConversationList() {
  const { conversationId, loadConversation, newConversation } = useChatContext();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);

  const refresh = useCallback(async () => {
    try {
      const data = await getConversations();
      setConversations(data);
    } catch {
      // API not available yet
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh, conversationId]);

  const handleSelect = useCallback(
    async (id: string) => {
      if (id === conversationId) return;
      try {
        const convo = await getConversation(id);
        loadConversation(id, convo.messages);
      } catch {
        // ignore
      }
    },
    [conversationId, loadConversation]
  );

  const handleDelete = useCallback(
    async (e: React.MouseEvent, id: string) => {
      e.stopPropagation();
      try {
        await deleteConversation(id);
        if (id === conversationId) newConversation();
        refresh();
      } catch {
        // ignore
      }
    },
    [conversationId, newConversation, refresh]
  );

  return (
    <div className="flex flex-col gap-0.5">
      <button
        onClick={newConversation}
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-accent hover:bg-accent-glow transition-all font-medium"
      >
        <Plus className="w-3.5 h-3.5" />
        New chat
      </button>
      {conversations.map((c) => (
        <button
          key={c.conversation_id}
          onClick={() => handleSelect(c.conversation_id)}
          className={cn(
            "group flex items-center gap-2 px-3 py-2 rounded-lg text-[11px] text-left transition-all",
            c.conversation_id === conversationId
              ? "bg-card text-text"
              : "text-text-muted hover:bg-card hover:text-text"
          )}
        >
          <MessageSquare className="w-3 h-3 shrink-0 text-text-dim" />
          <span className="flex-1 truncate leading-snug">
            {c.preview || "Empty conversation"}
          </span>
          <Trash2
            className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 text-text-dim hover:text-danger transition-all"
            onClick={(e) => handleDelete(e, c.conversation_id)}
          />
        </button>
      ))}
    </div>
  );
}
