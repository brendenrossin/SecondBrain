"use client";

import { TaskTree } from "@/components/tasks/TaskTree";

export default function TasksPage(): React.JSX.Element {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-8 pt-6 pb-2">
        <div>
          <h1 className="text-xl font-bold text-text tracking-tight">Tasks</h1>
          <p className="text-[13px] text-text-muted mt-0.5">
            Mission control for everything on your plate
          </p>
        </div>
      </div>
      <div className="overflow-y-auto flex-1 px-4 md:px-8 pb-6 pt-4">
        <TaskTree />
      </div>
    </div>
  );
}
