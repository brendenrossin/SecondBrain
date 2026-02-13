"use client";

import { useMemo, useState } from "react";
import { cn, extractTitle } from "@/lib/utils";
import type { EntityWithSource } from "@/lib/types";
import { ENTITY_EMOJI } from "@/lib/constants";

const TYPE_LABELS: Record<string, string> = {
  person: "People",
  org: "Organizations",
  product: "Products",
  place: "Places",
};

const FILTER_TABS = ["all", "person", "org", "product", "place"] as const;
type FilterTab = (typeof FILTER_TABS)[number];

interface GroupedEntity {
  text: string;
  type: string;
  notes: string[];
  maxConfidence: number;
}

export function EntityBrowser({
  entities,
  onSelectNote,
}: {
  entities: EntityWithSource[];
  onSelectNote: (path: string) => void;
}) {
  const [filter, setFilter] = useState<FilterTab>("all");

  // Group and deduplicate entities
  const grouped = useMemo(() => {
    const map = new Map<string, GroupedEntity>();
    for (const e of entities) {
      const key = `${e.text.toLowerCase()}|${e.entity_type}`;
      const existing = map.get(key);
      if (existing) {
        if (!existing.notes.includes(e.note_path)) {
          existing.notes.push(e.note_path);
        }
        existing.maxConfidence = Math.max(existing.maxConfidence, e.confidence);
      } else {
        map.set(key, {
          text: e.text,
          type: e.entity_type,
          notes: [e.note_path],
          maxConfidence: e.confidence,
        });
      }
    }
    return Array.from(map.values()).sort((a, b) =>
      a.text.localeCompare(b.text)
    );
  }, [entities]);

  const filtered = useMemo(() => {
    if (filter === "all") return grouped;
    return grouped.filter((g) => g.type === filter);
  }, [grouped, filter]);

  // Group by type for "all" view
  const byType = useMemo(() => {
    const map = new Map<string, GroupedEntity[]>();
    for (const g of filtered) {
      const group = map.get(g.type) || [];
      group.push(g);
      map.set(g.type, group);
    }
    return map;
  }, [filtered]);

  return (
    <div className="space-y-4">
      {/* Filter tabs */}
      <div className="flex gap-1 p-1 rounded-lg bg-card border border-border flex-wrap">
        {FILTER_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={cn(
              "px-3 py-1.5 rounded-md text-xs font-medium transition-all",
              filter === tab
                ? "bg-accent/15 text-accent"
                : "text-text-muted hover:text-text hover:bg-white/5"
            )}
          >
            {tab === "all" ? "All" : TYPE_LABELS[tab] || tab}
          </button>
        ))}
      </div>

      {/* Entity list */}
      {filtered.length === 0 ? (
        <p className="text-sm text-text-dim py-4">No entities found</p>
      ) : filter === "all" ? (
        // Grouped view
        <div className="space-y-4">
          {Array.from(byType.entries()).map(([type, items]) => (
            <div key={type} className="glass-card p-4">
              <h3 className="text-sm font-bold text-text mb-3">
                {ENTITY_EMOJI[type] || ""} {TYPE_LABELS[type] || type} (
                {items.length})
              </h3>
              <div className="space-y-2">
                {items.map((item) => (
                  <EntityRow
                    key={`${item.text}-${item.type}`}
                    entity={item}
                    onSelectNote={onSelectNote}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // Flat filtered view
        <div className="glass-card p-4 space-y-2">
          {filtered.map((item) => (
            <EntityRow
              key={`${item.text}-${item.type}`}
              entity={item}
              onSelectNote={onSelectNote}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EntityRow({
  entity,
  onSelectNote,
}: {
  entity: GroupedEntity;
  onSelectNote: (path: string) => void;
}) {
  const MAX_SHOW = 3;
  const shownNotes = entity.notes.slice(0, MAX_SHOW);
  const remaining = entity.notes.length - MAX_SHOW;

  return (
    <div className="flex items-start justify-between py-1.5 border-b border-border last:border-b-0">
      <div className="min-w-0">
        <span className="text-sm font-medium text-text">{entity.text}</span>
        <div className="text-xs text-text-dim mt-0.5">
          {shownNotes.map((path, i) => (
            <span key={path}>
              {i > 0 && ", "}
              <button
                onClick={() => onSelectNote(path)}
                className="hover:text-accent transition-colors"
              >
                {extractTitle(path)}
              </button>
            </span>
          ))}
          {remaining > 0 && (
            <span className="text-text-dim"> and {remaining} more</span>
          )}
        </div>
      </div>
    </div>
  );
}
