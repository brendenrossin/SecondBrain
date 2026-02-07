"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, CheckSquare, Calendar, MoreHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

const tabs = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/insights", label: "More", icon: MoreHorizontal },
];

export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex border-t border-border bg-surface/80 backdrop-blur-xl">
      {tabs.map((tab) => {
        const active = pathname === tab.href || pathname.startsWith(tab.href + "/");
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex-1 flex flex-col items-center gap-1 py-3 text-[10px] font-semibold transition-all duration-200",
              active ? "text-accent" : "text-text-dim"
            )}
          >
            <tab.icon className={cn("w-5 h-5", active && "drop-shadow-[0_0_8px_rgba(79,142,247,0.5)]")} />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
