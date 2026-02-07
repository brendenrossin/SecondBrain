"use client";

import { TaskTree } from "@/components/tasks/TaskTree";

export default function TasksPage() {
  return (
    <div className="h-full">
      <div className="flex items-center px-6 h-14 shrink-0 border-b border-border">
        <h1 className="text-base font-bold text-text tracking-tight">Tasks</h1>
      </div>
      <div className="overflow-y-auto px-6 pb-6 pt-5" style={{ height: "calc(100% - 3.5rem)" }}>
        <TaskTree />
      </div>
    </div>
  );
}
