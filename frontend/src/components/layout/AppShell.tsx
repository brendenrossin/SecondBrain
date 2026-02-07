"use client";

import { useMemo } from "react";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";
import { ErrorBoundary } from "../ErrorBoundary";
import { useChatContext } from "../providers/ChatProvider";
import { useKeyboardShortcuts } from "@/lib/useKeyboardShortcuts";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { newConversation } = useChatContext();

  const shortcuts = useMemo(
    () => ({
      onFocusChat: () => {
        const input = document.querySelector<HTMLTextAreaElement>(
          "[data-chat-input]"
        );
        input?.focus();
      },
      onNewConversation: newConversation,
    }),
    [newConversation]
  );
  useKeyboardShortcuts(shortcuts);

  return (
    <div className="flex h-screen w-screen overflow-hidden app-bg">
      <Sidebar />
      <main className="flex-1 overflow-y-auto pb-16 md:pb-0">
        <ErrorBoundary>{children}</ErrorBoundary>
      </main>
      <MobileNav />
    </div>
  );
}
