"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  CheckSquare,
  Calendar,
  Lightbulb,
  ChevronRight,
  Brain,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ConversationList } from "../chat/ConversationList";

/* ── Per-route color map (static strings for Tailwind purge) ── */
const NAV_COLORS: Record<string, {
  icon: string;
  iconActive: string;
  bgActive: string;
  borderActive: string;
  glowActive: string;
}> = {
  "/": {
    icon: "text-accent/60",
    iconActive: "text-accent drop-shadow-[0_0_6px_rgba(79,142,247,0.4)]",
    bgActive: "bg-accent/12",
    borderActive: "border-accent/15",
    glowActive: "shadow-[0_0_16px_rgba(79,142,247,0.1)]",
  },
  "/chat": {
    icon: "text-accent/60",
    iconActive: "text-accent drop-shadow-[0_0_6px_rgba(79,142,247,0.4)]",
    bgActive: "bg-accent/12",
    borderActive: "border-accent/15",
    glowActive: "shadow-[0_0_16px_rgba(79,142,247,0.1)]",
  },
  "/tasks": {
    icon: "text-success/60",
    iconActive: "text-success drop-shadow-[0_0_6px_rgba(52,211,153,0.4)]",
    bgActive: "bg-success/12",
    borderActive: "border-success/15",
    glowActive: "shadow-[0_0_16px_rgba(52,211,153,0.1)]",
  },
  "/calendar": {
    icon: "text-warning/60",
    iconActive: "text-warning drop-shadow-[0_0_6px_rgba(251,191,36,0.4)]",
    bgActive: "bg-warning/12",
    borderActive: "border-warning/15",
    glowActive: "shadow-[0_0_16px_rgba(251,191,36,0.1)]",
  },
  "/insights": {
    icon: "text-purple/60",
    iconActive: "text-purple drop-shadow-[0_0_6px_rgba(167,139,250,0.4)]",
    bgActive: "bg-purple/12",
    borderActive: "border-purple/15",
    glowActive: "shadow-[0_0_16px_rgba(167,139,250,0.1)]",
  },
};

const coreNavItems = [
  { href: "/", label: "Home", icon: LayoutDashboard },
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
      <div className="text-[10px] uppercase tracking-widest text-text-dim font-medium mt-6 mb-2.5 px-3">
        {label}
      </div>
      <div className="flex flex-col gap-1.5">
        {items.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(item.href + "/");
          const colors = NAV_COLORS[item.href];
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-medium transition-all duration-200",
                active
                  ? `${colors?.bgActive} text-text ${colors?.glowActive} border ${colors?.borderActive}`
                  : "text-text-muted hover:bg-white/[0.06] hover:text-text border border-transparent"
              )}
            >
              <item.icon
                className={cn(
                  "w-5 h-5 transition-colors",
                  active
                    ? colors?.iconActive
                    : `${colors?.icon} group-hover:text-text-muted`
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
    <aside className="hidden md:flex flex-col w-60 shrink-0 h-full border-r border-border bg-sidebar shadow-[2px_0_16px_rgba(0,0,0,0.3)]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 h-16 shrink-0">
        <div className="w-9 h-9 rounded-xl bg-accent/15 flex items-center justify-center shadow-[0_0_12px_rgba(79,142,247,0.15)]">
          <Brain className="w-5 h-5 text-accent" />
        </div>
        <div>
          <div className="font-bold text-sm text-text tracking-tight">Brent OS</div>
          <div className="text-[10px] text-text-dim font-medium">SecondBrain</div>
        </div>
      </div>

      {/* Grouped nav sections */}
      <nav className="flex flex-col flex-1 px-4">
        <NavSection label="Core" items={coreNavItems} pathname={pathname} />
        <NavSection label="Tools" items={toolsNavItems} pathname={pathname} />
      </nav>

      {/* History toggle */}
      <button
        onClick={() => setShowHistory(!showHistory)}
        className="flex items-center gap-2 px-6 py-3 mt-2 text-xs text-text-dim hover:text-text-muted transition-colors font-medium"
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
      <div className="flex items-center gap-3 px-5 py-4 mt-auto border-t border-border">
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
