"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Loader2 } from "lucide-react";
import { getSuggestions } from "@/lib/api";
import { extractTitle } from "@/lib/utils";
import { ENTITY_EMOJI } from "@/lib/constants";
import type { NoteMetadata, NoteSuggestions } from "@/lib/types";

const PRIORITY_STYLE: Record<string, { icon: string; color: string }> = {
  high: { icon: "\u26A1", color: "text-accent" },
  medium: { icon: "\u2022", color: "text-text" },
  low: { icon: "\u25CB", color: "text-text-dim" },
};

export function NoteDetail({
  metadata,
  onBack,
}: {
  metadata: NoteMetadata;
  onBack?: () => void;
}) {
  const [suggestions, setSuggestions] = useState<NoteSuggestions | null>(null);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadingSuggestions(true);
    setSuggestions(null);

    getSuggestions(metadata.note_path)
      .then((data) => {
        if (!cancelled) setSuggestions(data);
      })
      .catch(() => {
        if (!cancelled) setSuggestions(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingSuggestions(false);
      });

    return () => {
      cancelled = true;
    };
  }, [metadata.note_path]);

  const title = extractTitle(metadata.note_path);
  const extractedDate = metadata.extracted_at
    ? new Date(metadata.extracted_at).toLocaleDateString()
    : "";

  // Group entities by type
  const entityGroups = new Map<string, typeof metadata.entities>();
  for (const e of metadata.entities) {
    const group = entityGroups.get(e.entity_type) || [];
    group.push(e);
    entityGroups.set(e.entity_type, group);
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        {onBack && (
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-text-dim hover:text-text mb-3 md:hidden"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to list
          </button>
        )}
        <h2 className="text-lg font-bold text-text">{title}</h2>
        <p className="text-xs text-text-dim mt-0.5">{metadata.note_path}</p>
        {extractedDate && (
          <p className="text-xs text-text-dim mt-0.5">
            Extracted: {extractedDate} &middot; {metadata.model_used}
          </p>
        )}
      </div>

      {/* Summary */}
      {metadata.summary && (
        <div className="glass-card p-4">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
            Summary
          </h3>
          <p className="text-sm text-text leading-relaxed">
            {metadata.summary}
          </p>
        </div>
      )}

      {/* Key Phrases */}
      {metadata.key_phrases.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
            Key Phrases
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {metadata.key_phrases.map((phrase) => (
              <span
                key={phrase}
                className="px-2 py-0.5 rounded-full text-xs bg-accent/10 text-accent"
              >
                {phrase}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Entities */}
      {metadata.entities.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
            Entities
          </h3>
          <div className="space-y-2">
            {Array.from(entityGroups.entries()).map(([type, entities]) => (
              <div key={type}>
                <div className="flex flex-wrap gap-2">
                  {entities.map((e) => (
                    <span key={`${e.text}-${e.entity_type}`} className="text-sm text-text">
                      {ENTITY_EMOJI[type] || ""} {e.text}{" "}
                      <span className="text-text-dim text-xs">
                        ({e.confidence.toFixed(2)})
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dates */}
      {metadata.dates.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
            Dates
          </h3>
          <div className="space-y-1">
            {metadata.dates.map((d, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className="text-text">
                  {d.normalized_date || d.text}
                </span>
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-accent/10 text-accent uppercase">
                  {d.date_type}
                </span>
                <span className="text-text-dim text-xs">
                  ({d.confidence.toFixed(2)})
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Items */}
      {metadata.action_items.length > 0 && (
        <div className="glass-card p-4">
          <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
            Action Items
          </h3>
          <div className="space-y-1.5">
            {metadata.action_items.map((item, i) => {
              const style =
                PRIORITY_STYLE[item.priority || "medium"] ||
                PRIORITY_STYLE.medium;
              return (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className={style.color}>{style.icon}</span>
                  <span className="text-text">{item.text}</span>
                  {item.priority && (
                    <span className="text-text-dim text-xs">[{item.priority}]</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Connections (from suggestions API) */}
      <div className="glass-card p-4">
        <h3 className="text-xs font-bold text-text-dim uppercase tracking-wide mb-2">
          Connections
        </h3>

        {loadingSuggestions && (
          <div className="flex items-center gap-2 py-4 text-text-dim text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading connections...
          </div>
        )}

        {!loadingSuggestions && !suggestions && (
          <p className="text-sm text-text-dim">No suggestions available</p>
        )}

        {suggestions && (
          <div className="space-y-4">
            {/* Related Notes */}
            {suggestions.related_notes.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-text mb-1.5">
                  Related Notes
                </h4>
                <div className="space-y-1.5">
                  {suggestions.related_notes.map((rn) => (
                    <div key={rn.note_path} className="text-sm">
                      <span className="text-text font-medium">
                        {rn.note_title}
                      </span>{" "}
                      <span className="text-text-dim text-xs">
                        ({rn.similarity_score.toFixed(2)})
                      </span>
                      {rn.shared_entities.length > 0 && (
                        <p className="text-xs text-text-dim ml-4">
                          shared: {rn.shared_entities.join(", ")}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suggested Links */}
            {suggestions.suggested_links.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-text mb-1.5">
                  Suggested Links
                </h4>
                <div className="space-y-1.5">
                  {suggestions.suggested_links.map((sl) => (
                    <div key={sl.target_note_path} className="text-sm">
                      <span className="text-text font-medium">
                        &rarr; {sl.target_note_title}
                      </span>
                      <p className="text-xs text-text-dim ml-4">
                        &ldquo;{sl.anchor_text}&rdquo; ({sl.confidence.toFixed(2)})
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suggested Tags */}
            {suggestions.suggested_tags.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-text mb-1.5">
                  Suggested Tags
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {suggestions.suggested_tags.map((st) => (
                    <span
                      key={st.tag}
                      className="px-2 py-0.5 rounded-full text-xs bg-purple/10 text-purple"
                    >
                      #{st.tag}{" "}
                      <span className="opacity-60">
                        ({st.confidence.toFixed(2)})
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {suggestions.related_notes.length === 0 &&
              suggestions.suggested_links.length === 0 &&
              suggestions.suggested_tags.length === 0 && (
                <p className="text-sm text-text-dim">
                  No connections found for this note
                </p>
              )}
          </div>
        )}
      </div>
    </div>
  );
}
