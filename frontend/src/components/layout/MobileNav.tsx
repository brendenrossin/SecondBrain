"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Feather,
  MessageSquare,
  CheckSquare,
  Calendar,
  Lightbulb,
  Shield,
  Settings,
  MoreHorizontal,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

const primaryTabs = [
  { href: "/", label: "Home", icon: LayoutDashboard, color: "text-accent", glow: "drop-shadow-[0_0_8px_rgba(79,142,247,0.5)]" },
  { href: "/capture", label: "Capture", icon: Feather, color: "text-accent", glow: "drop-shadow-[0_0_8px_rgba(79,142,247,0.5)]" },
  { href: "/chat", label: "Chat", icon: MessageSquare, color: "text-accent", glow: "drop-shadow-[0_0_8px_rgba(79,142,247,0.5)]" },
  { href: "/tasks", label: "Tasks", icon: CheckSquare, color: "text-success", glow: "drop-shadow-[0_0_8px_rgba(52,211,153,0.5)]" },
];

const moreItems = [
  { href: "/calendar", label: "Calendar", icon: Calendar, color: "text-warning" },
  { href: "/insights", label: "Insights", icon: Lightbulb, color: "text-purple" },
  { href: "/admin", label: "Admin", icon: Shield, color: "text-text-muted" },
  { href: "/settings", label: "Settings", icon: Settings, color: "text-zinc-400" },
];

export function MobileNav(): React.JSX.Element {
  const pathname = usePathname();
  const [showMore, setShowMore] = useState(false);

  // Close the menu when navigating
  useEffect(() => {
    setShowMore(false);
  }, [pathname]);

  const moreActive = moreItems.some(
    (item) => pathname === item.href || pathname.startsWith(item.href + "/")
  );

  return (
    <>
      {/* More menu overlay */}
      {showMore && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setShowMore(false)}
        />
      )}

      {/* More menu sheet */}
      {showMore && (
        <div className="md:hidden fixed bottom-16 left-3 right-3 z-50 rounded-2xl bg-surface border border-border shadow-[0_-4px_24px_rgba(0,0,0,0.4)] p-2">
          {moreItems.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-medium transition-all",
                  active
                    ? `${item.color} bg-white/[0.06]`
                    : "text-text-muted"
                )}
              >
                <item.icon className="w-5 h-5" />
                {item.label}
              </Link>
            );
          })}
        </div>
      )}

      {/* Bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex border-t border-border bg-surface/80 backdrop-blur-xl">
        {primaryTabs.map((tab) => {
          const active =
            tab.href === "/"
              ? pathname === "/"
              : pathname === tab.href || pathname.startsWith(tab.href + "/");
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex-1 flex flex-col items-center gap-1 py-3 text-[10px] font-semibold transition-all duration-200",
                active ? tab.color : "text-text-dim"
              )}
            >
              <tab.icon className={cn("w-5 h-5", active && tab.glow)} />
              {tab.label}
            </Link>
          );
        })}

        {/* More button */}
        <button
          onClick={() => setShowMore(!showMore)}
          className={cn(
            "flex-1 flex flex-col items-center gap-1 py-3 text-[10px] font-semibold transition-all duration-200",
            showMore || moreActive ? "text-purple" : "text-text-dim"
          )}
        >
          {showMore ? (
            <X className="w-5 h-5 drop-shadow-[0_0_8px_rgba(167,139,250,0.5)]" />
          ) : (
            <MoreHorizontal className={cn("w-5 h-5", moreActive && "drop-shadow-[0_0_8px_rgba(167,139,250,0.5)]")} />
          )}
          More
        </button>
      </nav>
    </>
  );
}
