"use client";

import { useEffect, useRef, useState } from "react";
import { X, Circle, CircleDot, CheckCircle2 } from "lucide-react";
import type { TaskResponse, TaskCategory } from "@/lib/types";
import { updateTask, getTaskCategories } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TaskDetailPanelProps {
  task: TaskResponse;
  onClose: () => void;
  onUpdate: () => void;
}

const STATUS_OPTIONS = [
  { value: "open" as const, label: "Open", icon: Circle, color: "text-text-dim" },
  { value: "in_progress" as const, label: "In Progress", icon: CircleDot, color: "text-accent" },
  { value: "done" as const, label: "Done", icon: CheckCircle2, color: "text-success" },
];

export function TaskDetailPanel({ task, onClose, onUpdate }: TaskDetailPanelProps): React.JSX.Element {
  const [saving, setSaving] = useState(false);
  const [categories, setCategories] = useState<TaskCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState(task.category);
  const [selectedSubProject, setSelectedSubProject] = useState(task.sub_project);
  const [newCategoryInput, setNewCategoryInput] = useState("");
  const [newSubProjectInput, setNewSubProjectInput] = useState("");
  const [showNewCategory, setShowNewCategory] = useState(false);
  const [showNewSubProject, setShowNewSubProject] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getTaskCategories().then(setCategories).catch(() => {});
  }, []);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [onClose]);

  async function handleStatusChange(newStatus: "open" | "in_progress" | "done") {
    if (saving || newStatus === task.status) return;
    setSaving(true);
    try {
      await updateTask({
        text: task.text,
        category: task.category,
        sub_project: task.sub_project,
        status: newStatus,
      });
      onUpdate();
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  }

  async function handleDueDateChange(e: React.ChangeEvent<HTMLInputElement>) {
    const newDate = e.target.value; // "" if cleared, "YYYY-MM-DD" if set
    setSaving(true);
    try {
      await updateTask({
        text: task.text,
        category: task.category,
        sub_project: task.sub_project,
        due_date: newDate,
      });
      onUpdate();
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  }

  async function handleCategoryChange(newCat: string, newSub: string | null) {
    if (saving) return;
    if (newCat === task.category && (newSub ?? task.sub_project) === task.sub_project) return;
    setSaving(true);
    try {
      await updateTask({
        text: task.text,
        category: task.category,
        sub_project: task.sub_project,
        new_category: newCat,
        new_sub_project: newSub ?? "",
      });
      setSelectedCategory(newCat);
      setSelectedSubProject(newSub ?? "");
      onUpdate();
    } catch {
      // Revert to original values on failure
      setSelectedCategory(task.category);
      setSelectedSubProject(task.sub_project);
    } finally {
      setSaving(false);
    }
  }

  function handleCategorySelect(value: string) {
    if (value === "__new__") {
      setShowNewCategory(true);
      setNewCategoryInput("");
      return;
    }
    setShowNewCategory(false);
    setSelectedCategory(value);
    setSelectedSubProject("");
    setShowNewSubProject(false);
    handleCategoryChange(value, "");
  }

  function handleSubProjectSelect(value: string) {
    if (value === "__new__") {
      setShowNewSubProject(true);
      setNewSubProjectInput("");
      return;
    }
    setShowNewSubProject(false);
    const sub = value === "__none__" ? "" : value;
    setSelectedSubProject(sub);
    handleCategoryChange(selectedCategory, sub);
  }

  function handleNewCategorySubmit() {
    const trimmed = newCategoryInput.trim();
    if (!trimmed) return;
    setShowNewCategory(false);
    setSelectedCategory(trimmed);
    setSelectedSubProject("");
    setShowNewSubProject(false);
    handleCategoryChange(trimmed, "");
  }

  function handleNewSubProjectSubmit() {
    const trimmed = newSubProjectInput.trim();
    if (!trimmed) return;
    setShowNewSubProject(false);
    setSelectedSubProject(trimmed);
    handleCategoryChange(selectedCategory, trimmed);
  }

  const currentCat = categories.find((c) => c.category === selectedCategory);
  const subProjects = currentCat?.sub_projects?.filter((s) => s.name) ?? [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        ref={panelRef}
        className="relative w-full max-w-md bg-surface border-l border-border shadow-2xl animate-in slide-in-from-right duration-200 overflow-y-auto"
      >
        <div className="flex items-center justify-between px-6 py-5 border-b border-border">
          <span className="text-xs font-semibold text-text-dim uppercase tracking-wider">Task Detail</span>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-white/[0.06] text-text-dim hover:text-text transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className={cn("px-6 py-6 space-y-6", saving && "opacity-60 pointer-events-none")}>
          {/* Task text */}
          <p className="text-base font-semibold text-text leading-relaxed">{task.text}</p>

          {/* Category selector */}
          <div>
            <span className="text-[10px] font-medium text-text-dim uppercase tracking-wider block mb-2.5">Category</span>
            {!showNewCategory ? (
              <select
                value={selectedCategory}
                onChange={(e) => handleCategorySelect(e.target.value)}
                className="w-full bg-white/[0.04] border border-border rounded-xl px-3.5 py-2.5 text-sm text-text focus:ring-1 focus:ring-accent/30 focus:border-accent/20 outline-none transition-all appearance-none"
              >
                {categories.map((c) => (
                  <option key={c.category} value={c.category}>{c.category}</option>
                ))}
                {/* Show current category even if not in open categories list */}
                {!categories.find((c) => c.category === task.category) && (
                  <option value={task.category}>{task.category}</option>
                )}
                <option value="__new__">New category...</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newCategoryInput}
                  onChange={(e) => setNewCategoryInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleNewCategorySubmit()}
                  placeholder="Category name"
                  autoFocus
                  className="flex-1 bg-white/[0.04] border border-border rounded-xl px-3.5 py-2.5 text-sm text-text focus:ring-1 focus:ring-accent/30 focus:border-accent/20 outline-none transition-all"
                />
                <button
                  onClick={handleNewCategorySubmit}
                  className="px-3 py-2 rounded-xl text-xs font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors"
                >
                  Add
                </button>
                <button
                  onClick={() => { setShowNewCategory(false); setSelectedCategory(task.category); }}
                  className="px-3 py-2 rounded-xl text-xs font-medium text-text-dim hover:text-text hover:bg-white/[0.04] transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Sub-project selector */}
          <div>
            <span className="text-[10px] font-medium text-text-dim uppercase tracking-wider block mb-2.5">Sub-project</span>
            {!showNewSubProject ? (
              <select
                value={selectedSubProject || "__none__"}
                onChange={(e) => handleSubProjectSelect(e.target.value)}
                className="w-full bg-white/[0.04] border border-border rounded-xl px-3.5 py-2.5 text-sm text-text focus:ring-1 focus:ring-accent/30 focus:border-accent/20 outline-none transition-all appearance-none"
              >
                <option value="__none__">None</option>
                {subProjects.map((s) => (
                  <option key={s.name} value={s.name}>{s.name}</option>
                ))}
                {/* Show current sub-project even if not in list */}
                {selectedSubProject && !subProjects.find((s) => s.name === selectedSubProject) && (
                  <option value={selectedSubProject}>{selectedSubProject}</option>
                )}
                <option value="__new__">New sub-project...</option>
              </select>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newSubProjectInput}
                  onChange={(e) => setNewSubProjectInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleNewSubProjectSubmit()}
                  placeholder="Sub-project name"
                  autoFocus
                  className="flex-1 bg-white/[0.04] border border-border rounded-xl px-3.5 py-2.5 text-sm text-text focus:ring-1 focus:ring-accent/30 focus:border-accent/20 outline-none transition-all"
                />
                <button
                  onClick={handleNewSubProjectSubmit}
                  className="px-3 py-2 rounded-xl text-xs font-medium bg-accent/20 text-accent hover:bg-accent/30 transition-colors"
                >
                  Add
                </button>
                <button
                  onClick={() => { setShowNewSubProject(false); setSelectedSubProject(task.sub_project); }}
                  className="px-3 py-2 rounded-xl text-xs font-medium text-text-dim hover:text-text hover:bg-white/[0.04] transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Status toggle */}
          <div>
            <span className="text-[10px] font-medium text-text-dim uppercase tracking-wider block mb-2.5">Status</span>
            <div className="flex gap-2">
              {STATUS_OPTIONS.map(({ value, label: optLabel, icon: Icon, color }) => (
                <button
                  key={value}
                  onClick={() => handleStatusChange(value)}
                  className={cn(
                    "flex items-center gap-2 px-3.5 py-2 rounded-xl text-[12px] font-medium transition-all",
                    task.status === value
                      ? "bg-white/[0.08] ring-1 ring-white/[0.12] text-text"
                      : "text-text-dim hover:text-text-muted hover:bg-white/[0.03]"
                  )}
                >
                  <Icon className={cn("w-3.5 h-3.5", task.status === value ? color : "")} />
                  {optLabel}
                </button>
              ))}
            </div>
          </div>

          {/* Due date */}
          <div>
            <span className="text-[10px] font-medium text-text-dim uppercase tracking-wider block mb-2.5">Due Date</span>
            <input
              type="date"
              value={task.due_date || ""}
              onChange={handleDueDateChange}
              className="w-full bg-white/[0.04] border border-border rounded-xl px-3.5 py-2.5 text-sm text-text focus:ring-1 focus:ring-accent/30 focus:border-accent/20 outline-none transition-all"
            />
          </div>

          {/* Metadata */}
          <div className="border-t border-border pt-5">
            <span className="text-[10px] font-medium text-text-dim uppercase tracking-wider block mb-3">Info</span>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <span className="text-text-dim block mb-0.5">Days Open</span>
                <span className="text-text font-medium">{task.days_open}</span>
              </div>
              <div>
                <span className="text-text-dim block mb-0.5">First Appeared</span>
                <span className="text-text font-medium">{task.first_date}</span>
              </div>
              <div>
                <span className="text-text-dim block mb-0.5">Last Seen</span>
                <span className="text-text font-medium">{task.latest_date}</span>
              </div>
              <div>
                <span className="text-text-dim block mb-0.5">Appearances</span>
                <span className="text-text font-medium">{task.appearance_count}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
