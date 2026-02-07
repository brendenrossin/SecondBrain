"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  CheckSquare,
  Calendar,
  Lightbulb,
  ChevronRight,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConversationList } from "../chat/ConversationList";

const coreNavItems = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/calendar", label: "Calendar", icon: Calendar },
];

const toolsNavItems = [
  { href: "/insights", label: "Insights", icon: Lightbulb },
];

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavSectionProps {
  label: string;
  items: NavItem[];
  pathname: string;
}

function NavSection({ label, items, pathname }: NavSectionProps): React.JSX.Element {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-text-dim font-medium mt-7 mb-3 px-3">
        {label}
      </div>
      <div className="flex flex-col gap-1.5">
        {items.map((item) => {
          const active =
            pathname === item.href ||
            pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200",
                active
                  ? "bg-accent/12 text-accent shadow-[0_0_16px_rgba(79,142,247,0.1)] border border-accent/15"
                  : "text-text-muted hover:bg-white/[0.06] hover:text-text border border-transparent"
              )}
            >
              <item.icon
                className={cn(
                  "w-[18px] h-[18px] transition-colors",
                  active
                    ? "drop-shadow-[0_0_6px_rgba(79,142,247,0.4)]"
                    : "text-text-dim group-hover:text-text-muted"
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export function Sidebar(): React.JSX.Element {
  const pathname = usePathname();
  const [showHistory, setShowHistory] = useState(false);

  return (
    <aside className="hidden md:flex flex-col w-60 h-full border-r border-border bg-surface/90 backdrop-blur-xl shadow-[2px_0_16px_rgba(0,0,0,0.3)]">
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

      {/* Grouped nav sections */}
      <nav className="flex flex-col px-3">
        <NavSection label="Core" items={coreNavItems} pathname={pathname} />
        <NavSection label="Tools" items={toolsNavItems} pathname={pathname} />
      </nav>

      {/* History toggle */}
      <button
        onClick={() => setShowHistory(!showHistory)}
        className="flex items-center gap-2 px-5 py-3 mt-2 text-xs text-text-dim hover:text-text-muted transition-colors font-medium"
      >
        <ChevronRight
          className={cn(
            "w-3.5 h-3.5 transition-transform duration-200",
            showHistory && "rotate-90"
          )}
        />
        Recent Chats
      </button>
      {showHistory && (
        <div className="flex-1 overflow-y-auto px-3 pb-3 min-h-0">
          <ConversationList />
        </div>
      )}

      {/* User area */}
      <div className="flex items-center gap-3 px-4 py-3 mt-auto border-t border-border">
        <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center">
          <span className="text-xs font-bold text-accent">B</span>
        </div>
        <div>
          <div className="text-xs font-semibold text-text">Brent</div>
          <div className="text-[10px] text-text-dim">Local</div>
        </div>
      </div>
    </aside>
  );
}
