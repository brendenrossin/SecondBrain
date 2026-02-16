"use client";

import { Settings } from "lucide-react";
import { CategoryManager } from "@/components/settings/CategoryManager";

export default function SettingsPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Settings className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">Settings</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <CategoryManager />
      </div>
    </div>
  );
}
