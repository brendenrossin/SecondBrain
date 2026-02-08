"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import type { Citation, ConversationMessage } from "@/lib/types";
import { askStream } from "@/lib/api";

type Provider = "openai" | "local";

interface ChatContextValue {
  messages: ConversationMessage[];
  conversationId: string | null;
  isStreaming: boolean;
  provider: Provider;
  setProvider: (p: Provider) => void;
  sendMessage: (content: string) => void;
  newConversation: () => void;
  loadConversation: (id: string, msgs: ConversationMessage[]) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext must be used within ChatProvider");
  return ctx;
}

const PROVIDER_KEY = "brentos-provider";

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [provider, setProviderState] = useState<Provider>(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem(PROVIDER_KEY) as Provider) || "openai";
    }
    return "openai";
  });
  const abortRef = useRef<AbortController | null>(null);

  const setProvider = useCallback((p: Provider) => {
    setProviderState(p);
    localStorage.setItem(PROVIDER_KEY, p);
  }, []);

  const newConversation = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setMessages([]);
    setConversationId(null);
    setIsStreaming(false);
  }, []);

  const loadConversation = useCallback(
    (id: string, msgs: ConversationMessage[]) => {
      if (abortRef.current) abortRef.current.abort();
      setMessages(msgs);
      setConversationId(id);
      setIsStreaming(false);
    },
    []
  );

  const sendMessage = useCallback(
    (content: string) => {
      if (isStreaming || !content.trim()) return;

      const userMsg: ConversationMessage = { role: "user", content };
      const assistantMsg: ConversationMessage = {
        role: "assistant",
        content: "",
        citations: [],
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      askStream(
        {
          query: content,
          conversation_id: conversationId,
          provider,
        },
        {
          onCitations: (citations: Citation[]) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = { ...last, citations };
              }
              return updated;
            });
          },
          onToken: (token: string) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + token,
                };
              }
              return updated;
            });
          },
          onDone: (data) => {
            setConversationId(data.conversation_id);
            setIsStreaming(false);
            abortRef.current = null;
          },
          onError: (err) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: `Error: ${err.message}`,
                };
              }
              return updated;
            });
            setIsStreaming(false);
            abortRef.current = null;
          },
        },
        controller.signal
      ).catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: `Error: ${err.message}`,
            };
          }
          return updated;
        });
        setIsStreaming(false);
        abortRef.current = null;
      });
    },
    [conversationId, isStreaming, provider]
  );

  return (
    <ChatContext.Provider
      value={{
        messages,
        conversationId,
        isStreaming,
        provider,
        setProvider,
        sendMessage,
        newConversation,
        loadConversation,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}
