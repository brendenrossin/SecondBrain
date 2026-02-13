"use client";

import { useEffect, useState, useCallback } from "react";
import { FileText, Users, Tag, Zap, RefreshCw } from "lucide-react";
import { cn, extractTitle, extractFolder } from "@/lib/utils";
import { listMetadata, listEntities, listActionItems } from "@/lib/api";
import type {
  NoteMetadata,
  EntityWithSource,
  ActionItemWithSource,
} from "@/lib/types";
import { StatCard } from "@/components/StatCard";
import { NoteDetail } from "./NoteDetail";
import { EntityBrowser } from "./EntityBrowser";

type Tab = "notes" | "entities";

export function InsightsDashboard() {
  const [allMetadata, setAllMetadata] = useState<NoteMetadata[]>([]);
  const [entities, setEntities] = useState<EntityWithSource[]>([]);
  const [actionItems, setActionItems] = useState<ActionItemWithSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>("notes");
  const [selectedNotePath, setSelectedNotePath] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [meta, entityData, actionData] = await Promise.all([
        listMetadata(0, 200),
        listEntities(),
        listActionItems(),
      ]);
      setAllMetadata(meta);
      setEntities(entityData.entities);
      setActionItems(actionData.action_items);
    } catch (err) {
      console.error("Failed to load insights data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Compute stats
  const uniqueKeyPhrases = new Set(allMetadata.flatMap((m) => m.key_phrases))
    .size;
  const highPriorityCount = actionItems.filter(
    (a) => a.priority === "high"
  ).length;

  // Deduplicate entities and count by type for stat subtitle
  const seen = new Set<string>();
  const typeBreakdown = new Map<string, number>();
  for (const e of entities) {
    const key = `${e.text.toLowerCase()}|${e.entity_type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    typeBreakdown.set(e.entity_type, (typeBreakdown.get(e.entity_type) || 0) + 1);
  }
  const uniqueEntityCount = seen.size;
  const entitySubtitle = Array.from(typeBreakdown.entries())
    .map(([type, count]) => `${count} ${type}`)
    .join(", ");

  const selectedMetadata = selectedNotePath
    ? allMetadata.find((m) => m.note_path === selectedNotePath) || null
    : null;

  // Sort notes alphabetically
  const sortedMetadata = [...allMetadata].sort((a, b) =>
    extractTitle(a.note_path).localeCompare(extractTitle(b.note_path))
  );

  function handleSelectNoteFromEntity(path: string) {
    setSelectedNotePath(path);
    setActiveTab("notes");
  }

  return (
    <div className="space-y-6">
      {/* Header row: tab switcher + refresh */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 rounded-lg bg-card border border-border">
          {(["notes", "entities"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-medium transition-all capitalize",
                activeTab === tab
                  ? "bg-accent/15 text-accent"
                  : "text-text-muted hover:text-text hover:bg-white/5"
              )}
            >
              {tab}
            </button>
          ))}
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="p-2 rounded-lg text-text-dim hover:text-text hover:bg-white/5 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={FileText}
          label="Notes Extracted"
          value={loading ? "--" : String(allMetadata.length)}
          subValue={
            loading
              ? undefined
              : `${allMetadata.filter((m) => m.summary).length} with summaries`
          }
          color="bg-accent/15 text-accent"
        />
        <StatCard
          icon={Users}
          label="Entities"
          value={loading ? "--" : String(uniqueEntityCount)}
          subValue={loading ? undefined : entitySubtitle || "none extracted"}
          color="bg-purple/15 text-purple"
        />
        <StatCard
          icon={Tag}
          label="Key Phrases"
          value={loading ? "--" : String(uniqueKeyPhrases)}
          subValue={
            loading
              ? undefined
              : `across ${allMetadata.length} notes`
          }
          color="bg-success/15 text-success"
        />
        <StatCard
          icon={Zap}
          label="Action Items"
          value={loading ? "--" : String(actionItems.length)}
          subValue={
            loading
              ? undefined
              : highPriorityCount > 0
                ? `${highPriorityCount} high priority`
                : "none high priority"
          }
          color="bg-warning/15 text-warning"
        />
      </div>

      {/* Tab content */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card p-5 animate-pulse">
              <div className="h-4 bg-border/50 rounded w-1/3 mb-2" />
              <div className="h-3 bg-border/30 rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : activeTab === "notes" ? (
        allMetadata.length === 0 ? (
          <div className="glass-card p-8 text-center">
            <p className="text-sm text-text-dim">
              No notes have been extracted yet. Run{" "}
              <code className="px-1.5 py-0.5 rounded bg-card text-accent text-xs">
                make extract
              </code>{" "}
              or wait for the next daily sync.
            </p>
          </div>
        ) : (
          <div className="md:grid md:grid-cols-[2fr_3fr] md:gap-6">
            {/* Note list (hide on mobile when a note is selected) */}
            <div
              className={cn(
                "space-y-2 overflow-y-auto max-h-[70vh]",
                selectedNotePath ? "hidden md:block" : "block"
              )}
            >
              {sortedMetadata.map((meta) => {
                const title = extractTitle(meta.note_path);
                const folder = extractFolder(meta.note_path);
                const isSelected = meta.note_path === selectedNotePath;

                return (
                  <button
                    key={meta.note_path}
                    onClick={() => setSelectedNotePath(meta.note_path)}
                    className={cn(
                      "w-full text-left glass-card p-4 transition-all",
                      isSelected
                        ? "border-accent/30 bg-accent/5"
                        : "hover:bg-white/5"
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-text truncate">
                        {title}
                      </span>
                      {folder && (
                        <span className="text-[10px] font-medium text-accent/70 uppercase tracking-wider shrink-0">
                          {folder}
                        </span>
                      )}
                    </div>
                    {meta.summary && (
                      <p className="text-xs text-text-dim line-clamp-2">
                        {meta.summary}
                      </p>
                    )}
                    <div className="flex gap-3 mt-1.5 text-[10px] text-text-dim">
                      {meta.entities.length > 0 && (
                        <span>{meta.entities.length} entities</span>
                      )}
                      {meta.action_items.length > 0 && (
                        <span>{meta.action_items.length} action items</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Detail panel */}
            <div
              className={cn(
                selectedNotePath ? "block" : "hidden md:block"
              )}
            >
              {selectedMetadata ? (
                <NoteDetail
                  metadata={selectedMetadata}
                  onBack={() => setSelectedNotePath(null)}
                />
              ) : (
                <div className="glass-card p-8 text-center">
                  <p className="text-sm text-text-dim">
                    Select a note to view its metadata and connections
                  </p>
                </div>
              )}
            </div>
          </div>
        )
      ) : (
        <EntityBrowser
          entities={entities}
          onSelectNote={handleSelectNoteFromEntity}
        />
      )}
    </div>
  );
}
