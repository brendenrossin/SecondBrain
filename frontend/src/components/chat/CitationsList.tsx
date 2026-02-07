"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, BookOpen } from "lucide-react";
import type { Citation } from "@/lib/types";
import { CitationCard } from "./CitationCard";

export function CitationsList({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);

  if (!citations.length) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text transition-colors"
      >
        <BookOpen className="w-3 h-3" />
        {expanded ? (
          <ChevronDown className="w-3 h-3" />
        ) : (
          <ChevronRight className="w-3 h-3" />
        )}
        {citations.length} source{citations.length !== 1 ? "s" : ""}
      </button>
      {expanded && (
        <div className="flex flex-col gap-2 mt-2">
          {citations.map((c) => (
            <CitationCard key={c.chunk_id} citation={c} />
          ))}
        </div>
      )}
    </div>
  );
}
