"use client";

import { FileText } from "lucide-react";
import type { Citation } from "@/lib/types";

export function CitationCard({ citation }: { citation: Citation }) {
  const headingPath = citation.heading_path.join(" > ");

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5 text-xs">
      <div className="flex items-center gap-2 mb-1.5">
        <div className="w-5 h-5 rounded-md bg-accent-glow flex items-center justify-center shrink-0">
          <FileText className="w-3 h-3 text-accent" />
        </div>
        <span className="font-medium text-text truncate">
          {citation.note_title}
        </span>
      </div>
      {headingPath && (
        <div className="text-text-dim mb-1.5 truncate text-[10px]">{headingPath}</div>
      )}
      <p className="text-text-muted line-clamp-2 leading-relaxed">
        {citation.snippet}
      </p>
      <div className="flex gap-3 mt-2 text-[10px] text-text-dim">
        <span className="px-1.5 py-0.5 rounded bg-card-hover">sim: {citation.similarity_score.toFixed(2)}</span>
        <span className="px-1.5 py-0.5 rounded bg-card-hover">rank: {citation.rerank_score.toFixed(2)}</span>
      </div>
    </div>
  );
}
