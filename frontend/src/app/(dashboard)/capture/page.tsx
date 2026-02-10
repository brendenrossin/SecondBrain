"use client";

import { Feather } from "lucide-react";
import { CaptureForm } from "@/components/capture/CaptureForm";

export default function CapturePage(): React.JSX.Element {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Feather className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">
          Quick Capture
        </h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <CaptureForm />
      </div>
    </div>
  );
}
