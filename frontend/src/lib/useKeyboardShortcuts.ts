"use client";

import { useEffect } from "react";

export function useKeyboardShortcuts(callbacks: {
  onFocusChat?: () => void;
  onNewConversation?: () => void;
}) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey;

      // Cmd+K → focus chat input
      if (meta && e.key === "k") {
        e.preventDefault();
        callbacks.onFocusChat?.();
      }

      // Cmd+N → new conversation
      if (meta && e.key === "n") {
        e.preventDefault();
        callbacks.onNewConversation?.();
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [callbacks]);
}
