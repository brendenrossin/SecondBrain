"use client";

export function StreamingIndicator() {
  return (
    <span className="inline-flex items-center gap-1.5 py-1">
      <span className="w-2 h-2 rounded-full bg-accent/60 animate-bounce [animation-delay:0ms]" />
      <span className="w-2 h-2 rounded-full bg-accent/60 animate-bounce [animation-delay:150ms]" />
      <span className="w-2 h-2 rounded-full bg-accent/60 animate-bounce [animation-delay:300ms]" />
    </span>
  );
}
