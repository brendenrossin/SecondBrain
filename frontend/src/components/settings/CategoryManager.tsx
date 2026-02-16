"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronRight,
  Pencil,
  Plus,
  Trash2,
  Check,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getCategories,
  updateCategories,
  type CategoryConfig,
} from "@/lib/api";

/* ── Inline confirmation dialog ── */
function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative glass-card p-6 max-w-sm w-full mx-4">
        <p className="text-sm text-text mb-5">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 text-xs font-medium bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Subcategory row ── */
function SubcategoryRow({
  name,
  description,
  onEdit,
  onDelete,
}: {
  name: string;
  description: string;
  onEdit: (newName: string, newDesc: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(name);
  const [editDesc, setEditDesc] = useState(description);

  function save() {
    const trimmed = editName.trim();
    if (!trimmed) return;
    onEdit(trimmed, editDesc.trim());
    setEditing(false);
  }

  if (editing) {
    return (
      <div className="flex items-center gap-2 py-1.5 pl-4">
        <input
          autoFocus
          value={editName}
          onChange={(e) => setEditName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          className="w-28 bg-white/[0.06] border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-accent/40"
          placeholder="Name"
        />
        <input
          value={editDesc}
          onChange={(e) => setEditDesc(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
          className="flex-1 bg-white/[0.06] border border-border rounded-md px-2 py-1 text-xs text-text focus:outline-none focus:border-accent/40"
          placeholder="Description"
        />
        <button onClick={save} className="p-1 text-success hover:text-success/80">
          <Check className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => { setEditing(false); setEditName(name); setEditDesc(description); }}
          className="p-1 text-text-dim hover:text-text-muted"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div className="group flex items-center gap-2 py-1.5 pl-4 hover:bg-white/[0.02] rounded-md">
      <span className="text-xs font-medium text-text-muted w-28 shrink-0">{name}</span>
      <span className="text-xs text-text-dim flex-1 truncate">{description}</span>
      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={() => setEditing(true)} className="p-1 text-text-dim hover:text-text-muted">
          <Pencil className="w-3 h-3" />
        </button>
        <button onClick={onDelete} className="p-1 text-text-dim hover:text-red-400">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

/* ── Main CategoryManager ── */
export function CategoryManager() {
  const [categories, setCategories] = useState<CategoryConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editCategoryName, setEditCategoryName] = useState("");
  const [newCategoryName, setNewCategoryName] = useState("");
  const [newSubName, setNewSubName] = useState("");
  const [newSubDesc, setNewSubDesc] = useState("");
  const [confirm, setConfirm] = useState<{ message: string; action: () => void } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => setError("Failed to load categories"))
      .finally(() => setLoading(false));
  }, []);

  const persist = useCallback(async (updated: CategoryConfig[]) => {
    setCategories(updated);
    setError(null);
    try {
      await updateCategories(updated);
    } catch {
      setError("Failed to save — check your connection");
    }
  }, []);

  /* ── Category CRUD ── */
  function addCategory() {
    const trimmed = newCategoryName.trim();
    if (!trimmed || categories.some((c) => c.name === trimmed)) return;
    persist([...categories, { name: trimmed, sub_projects: {} }]);
    setNewCategoryName("");
  }

  function deleteCategory(name: string) {
    setConfirm({
      message: `Delete "${name}"? Existing tasks in this category will become Uncategorized.`,
      action: () => {
        persist(categories.filter((c) => c.name !== name));
        if (expandedCategory === name) setExpandedCategory(null);
        setConfirm(null);
      },
    });
  }

  function startEditCategory(name: string) {
    setEditingCategory(name);
    setEditCategoryName(name);
  }

  function saveEditCategory(oldName: string) {
    const trimmed = editCategoryName.trim();
    if (!trimmed) return;
    persist(
      categories.map((c) =>
        c.name === oldName ? { ...c, name: trimmed } : c
      )
    );
    if (expandedCategory === oldName) setExpandedCategory(trimmed);
    setEditingCategory(null);
  }

  /* ── Subcategory CRUD ── */
  function addSubcategory(catName: string) {
    const trimmed = newSubName.trim();
    if (!trimmed) return;
    persist(
      categories.map((c) => {
        if (c.name !== catName) return c;
        return { ...c, sub_projects: { ...c.sub_projects, [trimmed]: newSubDesc.trim() } };
      })
    );
    setNewSubName("");
    setNewSubDesc("");
  }

  function deleteSubcategory(catName: string, subName: string) {
    setConfirm({
      message: `Delete "${subName}"? Existing tasks will remain under ${catName} without a subcategory.`,
      action: () => {
        persist(
          categories.map((c) => {
            if (c.name !== catName) return c;
            const { [subName]: _, ...rest } = c.sub_projects;
            return { ...c, sub_projects: rest };
          })
        );
        setConfirm(null);
      },
    });
  }

  function editSubcategory(catName: string, oldName: string, newName: string, newDesc: string) {
    persist(
      categories.map((c) => {
        if (c.name !== catName) return c;
        const entries = Object.entries(c.sub_projects).map(([k, v]) =>
          k === oldName ? [newName, newDesc] : [k, v]
        );
        return { ...c, sub_projects: Object.fromEntries(entries) };
      })
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      {error && (
        <div className="glass-card glass-card-danger px-4 py-3 text-xs text-red-400">
          {error}
        </div>
      )}

      <div className="glass-card p-5">
        <h2 className="text-sm font-semibold text-text mb-1">Task Categories</h2>
        <p className="text-xs text-text-dim mb-4">
          Categories used by the inbox processor to classify captured notes. Changes apply to new captures only.
        </p>

        <div className="space-y-1">
          {categories.map((cat) => {
            const isExpanded = expandedCategory === cat.name;
            const isEditing = editingCategory === cat.name;
            const subCount = Object.keys(cat.sub_projects).length;

            return (
              <div key={cat.name} className="rounded-lg overflow-hidden">
                {/* Category row */}
                <div
                  className={cn(
                    "group flex items-center gap-2 px-3 py-2.5 rounded-lg transition-colors cursor-pointer",
                    isExpanded ? "bg-white/[0.04]" : "hover:bg-white/[0.03]"
                  )}
                  onClick={() => !isEditing && setExpandedCategory(isExpanded ? null : cat.name)}
                >
                  <ChevronRight
                    className={cn(
                      "w-3.5 h-3.5 text-text-dim transition-transform duration-200 shrink-0",
                      isExpanded && "rotate-90"
                    )}
                  />
                  {isEditing ? (
                    <input
                      autoFocus
                      value={editCategoryName}
                      onChange={(e) => setEditCategoryName(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEditCategory(cat.name);
                        if (e.key === "Escape") setEditingCategory(null);
                      }}
                      className="flex-1 bg-white/[0.06] border border-border rounded-md px-2 py-0.5 text-sm text-text focus:outline-none focus:border-accent/40"
                    />
                  ) : (
                    <span className="flex-1 text-sm font-medium text-text">{cat.name}</span>
                  )}
                  <span className="text-[10px] text-text-dim mr-1">
                    {subCount > 0 && `${subCount} sub`}
                  </span>
                  {isEditing ? (
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => saveEditCategory(cat.name)} className="p-1 text-success hover:text-success/80">
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => setEditingCategory(null)} className="p-1 text-text-dim hover:text-text-muted">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => startEditCategory(cat.name)} className="p-1 text-text-dim hover:text-text-muted">
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => deleteCategory(cat.name)} className="p-1 text-text-dim hover:text-red-400">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>

                {/* Expanded subcategories */}
                {isExpanded && (
                  <div className="pl-6 pr-3 pb-3 space-y-0.5">
                    {Object.entries(cat.sub_projects).map(([subName, subDesc]) => (
                      <SubcategoryRow
                        key={subName}
                        name={subName}
                        description={subDesc}
                        onEdit={(n, d) => editSubcategory(cat.name, subName, n, d)}
                        onDelete={() => deleteSubcategory(cat.name, subName)}
                      />
                    ))}
                    {subCount === 0 && (
                      <p className="text-[11px] text-text-dim pl-4 py-1.5">No subcategories</p>
                    )}
                    {/* Add subcategory */}
                    <div className="flex items-center gap-2 pt-2 pl-4">
                      <input
                        value={newSubName}
                        onChange={(e) => setNewSubName(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && addSubcategory(cat.name)}
                        className="w-28 bg-white/[0.06] border border-border rounded-md px-2 py-1 text-xs text-text placeholder:text-text-dim focus:outline-none focus:border-accent/40"
                        placeholder="Name"
                      />
                      <input
                        value={newSubDesc}
                        onChange={(e) => setNewSubDesc(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && addSubcategory(cat.name)}
                        className="flex-1 bg-white/[0.06] border border-border rounded-md px-2 py-1 text-xs text-text placeholder:text-text-dim focus:outline-none focus:border-accent/40"
                        placeholder="Description (for LLM prompt)"
                      />
                      <button
                        onClick={() => addSubcategory(cat.name)}
                        disabled={!newSubName.trim()}
                        className="p-1 text-accent hover:text-accent/80 disabled:text-text-dim disabled:cursor-not-allowed"
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Add category */}
        <div className="flex items-center gap-2 mt-4 pt-4 border-t border-border">
          <input
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCategory()}
            className="flex-1 bg-white/[0.06] border border-border rounded-md px-3 py-1.5 text-sm text-text placeholder:text-text-dim focus:outline-none focus:border-accent/40"
            placeholder="New category name..."
          />
          <button
            onClick={addCategory}
            disabled={!newCategoryName.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-accent/15 text-accent rounded-lg hover:bg-accent/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus className="w-3.5 h-3.5" />
            Add
          </button>
        </div>
      </div>

      {confirm && (
        <ConfirmDialog
          message={confirm.message}
          onConfirm={confirm.action}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
