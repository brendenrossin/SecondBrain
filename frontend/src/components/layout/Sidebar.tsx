"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  CheckSquare,
  Calendar,
  Lightbulb,
  ChevronDown,
  ChevronRight,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConversationList } from "../chat/ConversationList";

const navItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/insights", label: "Insights", icon: Lightbulb },
];

export function Sidebar() {
  const pathname = usePathname();
  const [showHistory, setShowHistory] = useState(false);

  return (
    <aside className="hidden md:flex flex-col w-60 h-full border-r border-border bg-surface/80 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 h-16 shrink-0">
        <div className="w-9 h-9 rounded-xl bg-accent/15 flex items-center justify-center shadow-[0_0_12px_rgba(79,142,247,0.15)]">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <div>
          <div className="font-bold text-sm text-text tracking-tight">Brent OS</div>
          <div className="text-[10px] text-text-dim font-medium">SecondBrain</div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex flex-col gap-1 px-3 mt-3">
        {navItems.map((item) => {
          const active =
            pathname === item.href ||
            pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200",
                active
                  ? "bg-accent/12 text-accent shadow-[0_0_16px_rgba(79,142,247,0.1)] border border-accent/15"
                  : "text-text-muted hover:bg-white/[0.04] hover:text-text border border-transparent"
              )}
            >
              <item.icon className={cn("w-[18px] h-[18px]", active && "drop-shadow-[0_0_6px_rgba(79,142,247,0.4)]")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* History toggle */}
      <div className="mt-auto border-t border-border mx-4" />
      <button
        onClick={() => setShowHistory(!showHistory)}
        className="flex items-center gap-2 px-5 py-3 text-xs text-text-dim hover:text-text-muted transition-colors font-medium"
      >
        {showHistory ? (
          <ChevronDown className="w-3.5 h-3.5" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5" />
        )}
        Recent Chats
      </button>
      {showHistory && (
        <div className="flex-1 overflow-y-auto px-3 pb-3 min-h-0">
          <ConversationList />
        </div>
      )}
    </aside>
  );
}
