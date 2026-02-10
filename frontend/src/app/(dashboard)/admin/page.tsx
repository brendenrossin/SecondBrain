"use client";

import { Shield } from "lucide-react";
import { AdminDashboard } from "@/components/admin/AdminDashboard";

export default function AdminPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Shield className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">Admin</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <AdminDashboard />
      </div>
    </div>
  );
}
