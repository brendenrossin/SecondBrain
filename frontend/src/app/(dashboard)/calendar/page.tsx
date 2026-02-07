"use client";

import { WeeklyAgenda } from "@/components/calendar/WeeklyAgenda";

export default function CalendarPage() {
  return (
    <div className="h-full">
      <div className="flex items-center px-6 h-14 border-b border-border shrink-0">
        <h1 className="text-base font-bold text-text tracking-tight">Calendar</h1>
      </div>
      <div className="overflow-y-auto px-6 pb-6 pt-5" style={{ height: "calc(100% - 3.5rem)" }}>
        <WeeklyAgenda />
      </div>
    </div>
  );
}
