# SecondBrain UI Design Specification — "Mission Control" Overhaul

> **Purpose:** This document is the single source of truth for the SecondBrain frontend visual redesign. Claude Code (or any agent) should follow this spec when modifying UI components. The goal is to transform the current functional-but-flat interface into a polished "dark mission control" dashboard.

> **Constraint:** This is a front-end-only redesign. Do not change backend behavior, API contracts, data flows, or state management. Keep all existing routes, props, and data fetching intact.

---

## 1. Design Vision & Reference

### Target Aesthetic
The target look is a **dark command center / mission control dashboard** — think the OpenClaw Mission Control UI, Linear.app, Vercel Dashboard, Raycast, or Supabase dashboard. The key feeling is: **calm authority, depth without clutter, professional but not sterile.**

### Reference Products (Study These)
When you need visual reference for any decision, look at these products:

| Product | What to Study | URL |
|---------|--------------|-----|
| **Linear** | Card depth, typography scale, subtle borders, color hierarchy | linear.app |
| **Vercel Dashboard** | Stat cards, clean data tables, minimal dividers, spacing | vercel.com/dashboard |
| **Raycast** | Sidebar navigation, dark theme execution, icon treatment | raycast.com |
| **Supabase Dashboard** | Table views, status badges, card layouts, glassmorphism | supabase.com/dashboard |
| **shadcn/ui** | Component patterns, dark theme tokens, accessible primitives | ui.shadcn.com |

### Design Inspiration Search Terms
If you need more reference, search Dribbble/Behance/Mobbin for:
- "dark dashboard sidebar stat cards"
- "mission control dashboard UI"
- "developer productivity dashboard dark UI"
- "AI agent dashboard glassmorphism"
- "dark mode kanban task dashboard"

---

## 2. What Makes the Target UI Look "Modern" (Gap Analysis)

### Current Problems
1. **Flat hierarchy** — page title is small, stat cards and task list compete for attention equally
2. **Dense/spreadsheet feel** — task rows separated by thin border lines, no breathing room
3. **Weak card depth** — glass-card exists but cards feel samey, no layered elevation system
4. **Missing page header** — no subtitle, no right-aligned actions, no page-level context
5. **Sparse sidebar** — nav works but lacks grouped sections, profile area, or polish
6. **No empty states** — "No tasks found" is plain text, no illustration or personality
7. **No loading skeletons** — just a spinner, feels unfinished
8. **Missing hover affordances** — hover states exist but are too subtle (0.02 opacity change)
9. **No micro-interactions** — no transitions on accordion open/close, no card lift on hover

### What the Target Gets Right
1. **Strong hierarchy** — big title + subtitle, dominant stat row, secondary list
2. **Cards with soft depth** — subtle gradients + blur + faint borders + layered shadows
3. **Spacing over lines** — padding and whitespace separate sections, not divider lines
4. **Consistent status language** — same small set of visual tokens everywhere (badge, icon, progress)
5. **Typography discipline** — title large/semibold, secondary muted/smaller, few competing sizes
6. **Hover polish** — slight card lift + brighter border, clean and predictable

---

## 3. Design Token System

### Current Tokens (Keep These — They're Good)
The existing `globals.css` `@theme` block has a solid foundation. Keep the semantic color system but **add these new tokens:**

```css
@theme {
  /* === EXISTING (keep all) === */
  --color-bg: #080a10;
  --color-bg-subtle: #0d1017;
  --color-surface: #111520;
  --color-surface-hover: #181d2c;
  --color-card: #141925;
  --color-card-hover: #1a2033;
  --color-border: rgba(255, 255, 255, 0.06);
  --color-border-light: rgba(255, 255, 255, 0.1);
  --color-text: #E8ECF4;
  --color-text-muted: #8B95AE;
  --color-text-dim: #5C6580;
  --color-accent: #4F8EF7;
  --color-accent-hover: #6BA1FF;
  --color-accent-glow: rgba(79, 142, 247, 0.15);
  --color-success: #34D399;
  --color-success-dim: rgba(52, 211, 153, 0.12);
  --color-warning: #FBBF24;
  --color-warning-dim: rgba(251, 191, 36, 0.12);
  --color-danger: #F87171;
  --color-danger-dim: rgba(248, 113, 113, 0.12);
  --color-purple: #A78BFA;
  --color-purple-dim: rgba(167, 139, 250, 0.12);
  --font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif;

  /* === NEW TOKENS TO ADD === */

  /* Elevated surfaces (for cards that sit above other cards) */
  --color-surface-elevated: #1a1f2e;

  /* Border for interactive/focused elements */
  --color-border-focus: rgba(79, 142, 247, 0.3);

  /* Skeleton loading shimmer */
  --color-skeleton: rgba(255, 255, 255, 0.04);
  --color-skeleton-shimmer: rgba(255, 255, 255, 0.08);

  /* Spacing scale (reference, use Tailwind equivalents) */
  /* xs: 4px, sm: 8px, md: 12px, lg: 16px, xl: 24px, 2xl: 32px, 3xl: 48px */

  /* Border radius scale */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
}
```

### Typography Scale (Enforce Consistently)

| Role | Size | Weight | Color | Tailwind |
|------|------|--------|-------|----------|
| Page title | 20px | 700 (bold) | `text` | `text-xl font-bold text-text` |
| Page subtitle | 13px | 400 | `text-muted` | `text-[13px] text-text-muted` |
| Section header | 14px | 700 | `text` | `text-sm font-bold text-text` |
| Card stat number | 28px | 700 | semantic color | `text-[28px] font-bold tracking-tight` |
| Card stat label | 11px | 500 | `text-dim` | `text-[11px] font-medium text-text-dim uppercase tracking-wider` |
| Task title | 13px | 500 | `text` | `text-[13px] font-medium text-text` |
| Task metadata | 11px | 500 | `text-dim` | `text-[11px] font-medium text-text-dim` |
| Badge text | 10px | 600 | semantic | `text-[10px] font-semibold` |
| Nav item | 13px | 500 | `text-muted` (inactive) / `accent` (active) | `text-[13px] font-medium` |

### Spacing Rules
- **Use 8px grid.** All padding and gaps should be multiples of 4px (Tailwind: 1=4px, 2=8px, 3=12px, 4=16px, 5=20px, 6=24px, 8=32px).
- **Section gaps:** 24px between major sections (stat row → filters → task list).
- **Card internal padding:** 20-24px (Tailwind `p-5` or `p-6`).
- **Task row height:** 48-52px (comfortable, not cramped).
- **Minimize visible divider lines.** Use spacing + card containers instead. Where dividers are needed, use `border-border` (the existing 6% opacity).

### Border Radius Rules
- **All cards:** `rounded-2xl` (16px) — this is already set in `.glass-card`, keep it.
- **Stat cards:** `rounded-xl` (12px) for slightly smaller feel.
- **Buttons/inputs:** `rounded-xl` (12px).
- **Badges:** `rounded-lg` (8px).
- **Icons in containers:** `rounded-lg` (8px) or `rounded-xl` (12px).

---

## 4. Component-by-Component Redesign Spec

### 4.1 App Shell (`AppShell.tsx`)

**Current:** `flex h-screen w-screen overflow-hidden app-bg` with Sidebar + main + MobileNav.

**Changes needed:**
- No structural changes. The layout is fine.
- Ensure main content has consistent padding: `px-8 py-6` on desktop (currently `px-6 pb-6 pt-5`).

### 4.2 Sidebar (`Sidebar.tsx`)

**Current state:** 240px, `bg-surface/80 backdrop-blur-xl`, brain logo, 4 nav items, collapsible recent chats.

**Target improvements:**

1. **Grouped navigation sections** — Add visual grouping:
   ```
   CORE
   ├── Chat
   ├── Tasks
   └── Calendar

   TOOLS
   ├── Insights
   └── (future items)
   ```
   Use a tiny `text-[10px] uppercase tracking-widest text-text-dim font-medium` section label with `mt-6 mb-2 px-3` spacing.

2. **Nav item polish:**
   - Active state is already good (accent glow + border). Keep it.
   - Inactive hover: increase from `bg-white/[0.04]` to `bg-white/[0.06]` for more visible feedback.
   - Add `group` class to nav links so child icons can react: on hover, icon goes from `text-text-dim` to `text-text-muted`.

3. **Profile/user area at bottom:**
   - Below the divider and "Recent Chats", add a small user area:
   ```tsx
   <div className="flex items-center gap-3 px-4 py-3 mt-auto border-t border-border">
     <div className="w-8 h-8 rounded-lg bg-accent/15 flex items-center justify-center">
       <span className="text-xs font-bold text-accent">B</span>
     </div>
     <div>
       <div className="text-xs font-semibold text-text">Brent</div>
       <div className="text-[10px] text-text-dim">Local</div>
     </div>
   </div>
   ```

4. **Sidebar dividers:** Replace the current `border-t border-border mx-4` divider with more spacing and less visible lines. Use `my-2` spacing between sections instead of hard lines where possible.

### 4.3 Tasks Page Header (`tasks/page.tsx`)

**Current:** Just "Tasks" in a 56px header bar with bottom border.

**Target:** Full mission-control header with title, subtitle, and actions.

```tsx
<div className="flex items-center justify-between px-8 pt-6 pb-2">
  <div>
    <h1 className="text-xl font-bold text-text tracking-tight">Tasks</h1>
    <p className="text-[13px] text-text-muted mt-0.5">
      Mission control for everything on your plate
    </p>
  </div>
  <div className="flex items-center gap-2">
    {/* Future: New Task, Sync, Settings buttons */}
    {/* For now, placeholder or omit */}
  </div>
</div>
```

**Remove** the `h-14 border-b border-border` header bar. Use spacing instead of a bottom border.

### 4.4 Stat Cards (`TaskTree.tsx` → `StatCard`)

**Current:** `stat-card` class with icon + label + big number. Functional but small and flat.

**Target:** Clickable stat cards that toggle filters, with more presence.

**Design for each stat card:**
```tsx
<button
  onClick={() => onFilterToggle(filterType)}
  className={cn(
    "stat-card flex flex-col gap-2 cursor-pointer transition-all duration-200",
    "hover:border-border-light hover:translate-y-[-2px]",
    "active:translate-y-0",
    isActive && "ring-1 ring-accent/30 border-accent/20",
    glowClass
  )}
>
  <div className="flex items-center justify-between">
    <div className="w-9 h-9 rounded-xl flex items-center justify-center"
         style={{ background: iconBgColor }}>
      <Icon className={`w-4.5 h-4.5 ${iconColor}`} />
    </div>
    <span className={`text-[28px] font-bold tracking-tight ${valueColor}`}>
      {value}
    </span>
  </div>
  <span className="text-[11px] font-medium text-text-dim uppercase tracking-wider">
    {label}
  </span>
</button>
```

**Key changes:**
- Icon gets a **container background** (e.g., `bg-accent/12` for Active, `bg-danger/12` for Overdue) — this is a huge visual upgrade for minimal effort.
- Number moves to top-right, icon to top-left → creates a **diagonal read pattern**.
- Card becomes a `<button>` for filter toggling.
- Hover: subtle lift (`translate-y-[-2px]`) + border brightens.
- Active filter state: faint ring/border in semantic color.

**Stat card grid:** Keep `grid grid-cols-2 md:grid-cols-4 gap-3`. Consider increasing gap to `gap-4`.

### 4.5 Task Filters (`TaskFilters.tsx`)

**Current:** Search input + "Show done" toggle. Clean but basic.

**Target improvements:**

1. **Search input polish:**
   - Increase height slightly: `py-3` instead of `py-2.5`.
   - Add a subtle placeholder animation or just ensure focus state is obvious.
   - Current focus state (`border-accent/30 + shadow`) is good. Keep it.

2. **Add filter chips** (future enhancement — stub now):
   ```tsx
   <div className="flex items-center gap-2 flex-wrap">
     {/* Status chip */}
     <button className="text-[11px] font-medium px-3 py-1.5 rounded-lg
                        border border-border bg-white/[0.02] text-text-muted
                        hover:bg-white/[0.04] hover:text-text transition-all">
       Status
     </button>
     {/* Project chip */}
     <button className="...same...">Project</button>
     {/* Due window chip */}
     <button className="...same...">Due date</button>
   </div>
   ```
   Even if non-functional initially, these **look modern** and signal interactivity.

3. **"Show done" button:** Current styling is fine. Consider renaming to just a toggle icon (eye/eye-off) to save space, or keep as-is.

### 4.6 Task Categories (`TaskCategory.tsx`)

**Current:** `glass-card` with chevron + category name + "X open" badge. Expands to show tasks with `border-t border-border`.

**Target improvements:**

1. **Remove the inner border-t divider** between header and task list. Use padding/spacing instead:
   ```tsx
   {expanded && (
     <div className="px-2 pb-2">
       {/* tasks render here with their own card-like containers */}
     </div>
   )}
   ```

2. **Category badge enhancement:**
   - Current badge (`text-accent bg-accent/10 px-2.5 py-1 rounded-lg`) is good.
   - Add the count more prominently: `{openCount} open` is fine, or just show the number.

3. **Accordion animation:**
   Add smooth height transition on expand/collapse. Use CSS:
   ```css
   .accordion-content {
     display: grid;
     grid-template-rows: 0fr;
     transition: grid-template-rows 200ms ease-out;
   }
   .accordion-content[data-expanded="true"] {
     grid-template-rows: 1fr;
   }
   .accordion-content > div {
     overflow: hidden;
   }
   ```
   Or use a simple `max-height` transition with overflow hidden.

4. **Chevron rotation animation:**
   ```tsx
   <ChevronRight className={cn(
     "w-4 h-4 text-text-dim transition-transform duration-200",
     expanded && "rotate-90"
   )} />
   ```
   Use only `ChevronRight` and rotate it, instead of swapping between ChevronDown/ChevronRight.

### 4.7 Task Items (`TaskItem.tsx`)

**Current:** Row with circle icon + text + days open + due badge, separated by `border-b border-border`.

**This is where the biggest visual improvement happens.**

**Target design:**
```tsx
<div className={cn(
  "flex items-center gap-3 px-4 py-3 mx-2 rounded-xl",
  "hover:bg-white/[0.03] transition-all duration-150",
  "group cursor-default"
)}>
  {/* Checkbox */}
  {task.completed ? (
    <CheckCircle2 className="w-[18px] h-[18px] text-success shrink-0" />
  ) : (
    <Circle className="w-[18px] h-[18px] text-text-dim shrink-0
                       group-hover:text-text-muted transition-colors" />
  )}

  {/* Title + metadata row */}
  <div className="flex-1 min-w-0">
    <p className={cn(
      "text-[13px] leading-snug font-medium truncate",
      task.completed ? "text-text-dim line-through" : "text-text"
    )}>
      {task.text}
    </p>
  </div>

  {/* Right side: metadata + badge */}
  <div className="flex items-center gap-3 shrink-0">
    {!task.completed && task.days_open > 0 && (
      <span className="text-[10px] text-text-dim font-medium tabular-nums">
        {task.days_open}d open
      </span>
    )}
    <DueBadge dueDate={task.due_date} />

    {/* Hover action: overflow menu (future) */}
    <button className="opacity-0 group-hover:opacity-100 transition-opacity
                       w-6 h-6 flex items-center justify-center rounded-md
                       hover:bg-white/[0.06] text-text-dim hover:text-text-muted">
      <MoreHorizontal className="w-3.5 h-3.5" />
    </button>
  </div>
</div>
```

**Key changes:**
1. **Remove `border-b` dividers between tasks.** Use rounded rows with hover background instead.
2. **Add `mx-2 rounded-xl`** to each row — rows become "hoverable cards within the parent card."
3. **Group hover** to reveal quick-action overflow menu.
4. **Slightly larger icons** (18px instead of 16px) for better touch targets.
5. **`truncate`** on task text to prevent overflow.

### 4.8 Due Badge (`DueBadge.tsx`)

**Current:** Works well. The color coding and sizing are good.

**Minor improvements:**
- Add `tabular-nums` class to numbers so they don't shift width.
- Consider adding a tiny dot indicator before the text for overdue items:
  ```tsx
  {isOverdue && (
    <span className="w-1.5 h-1.5 rounded-full bg-danger mr-1
                    animate-pulse shadow-[0_0_4px_rgba(248,113,113,0.5)]" />
  )}
  ```

### 4.9 Loading States

**Current:** Single `Loader2` spinner centered on page.

**Target:** Skeleton loading that mirrors the actual layout.

Create a `TaskSkeleton` component:
```tsx
function TaskSkeleton() {
  return (
    <div className="animate-pulse">
      {/* Stat cards skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="stat-card h-[88px]">
            <div className="flex items-center justify-between mb-3">
              <div className="w-9 h-9 rounded-xl bg-white/[0.04]" />
              <div className="w-10 h-7 rounded-lg bg-white/[0.04]" />
            </div>
            <div className="w-16 h-3 rounded bg-white/[0.04]" />
          </div>
        ))}
      </div>

      {/* Search skeleton */}
      <div className="h-11 rounded-xl bg-white/[0.03] border border-border mb-6" />

      {/* Category skeletons */}
      {[...Array(3)].map((_, i) => (
        <div key={i} className="glass-card mb-4 p-5">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded bg-white/[0.04]" />
            <div className="w-24 h-4 rounded bg-white/[0.04]" />
            <div className="ml-auto w-14 h-5 rounded-lg bg-white/[0.04]" />
          </div>
          <div className="mt-4 space-y-1">
            {[...Array(3 - i)].map((_, j) => (
              <div key={j} className="flex items-center gap-3 px-4 py-3">
                <div className="w-[18px] h-[18px] rounded-full bg-white/[0.04]" />
                <div className="flex-1 h-3.5 rounded bg-white/[0.04]" />
                <div className="w-14 h-5 rounded-lg bg-white/[0.04]" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

### 4.10 Empty States

**Current:** `"No tasks found"` in plain text.

**Target:** Friendly empty state with context:
```tsx
<div className="flex flex-col items-center justify-center py-16 text-center">
  <div className="w-14 h-14 rounded-2xl bg-accent/10 flex items-center justify-center mb-4">
    <CheckCircle2 className="w-7 h-7 text-accent/60" />
  </div>
  <p className="text-sm font-medium text-text-muted mb-1">All clear</p>
  <p className="text-xs text-text-dim">No tasks match your current filters.</p>
</div>
```

---

## 5. CSS Utility Classes to Add

Add these to `globals.css` alongside the existing `.glass-card` etc:

```css
/* Skeleton shimmer animation */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton-shimmer {
  background: linear-gradient(
    90deg,
    var(--color-skeleton) 25%,
    var(--color-skeleton-shimmer) 50%,
    var(--color-skeleton) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

/* Subtle card lift on hover */
.hover-lift {
  transition: transform 200ms ease, box-shadow 200ms ease, border-color 200ms ease;
}
.hover-lift:hover {
  transform: translateY(-2px);
  border-color: var(--color-border-light);
}

/* Stat card with icon container pattern */
.stat-card-v2 {
  background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%),
              var(--color-card);
  border: 1px solid var(--color-border);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  border-radius: 14px;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 200ms ease;
}
.stat-card-v2:hover {
  border-color: var(--color-border-light);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
}

/* Accordion smooth open/close */
.accordion-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 250ms ease-out;
}
.accordion-body.expanded {
  grid-template-rows: 1fr;
}
.accordion-body > div {
  overflow: hidden;
}

/* Focus ring for interactive elements */
.focus-ring:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
  border-radius: inherit;
}

/* Scrollbar on hover only */
.scroll-hover::-webkit-scrollbar-thumb {
  background: transparent;
}
.scroll-hover:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
}
```

---

## 6. Interaction & Animation Spec

### Hover States
- **Cards (stat, category):** `translateY(-2px)` + border brightens to `border-light` + shadow deepens. Duration: 200ms ease.
- **Task rows:** Background fades to `bg-white/[0.03]`. Duration: 150ms.
- **Nav items:** Background fades to `bg-white/[0.06]`. Duration: 200ms.
- **Buttons:** Background color shift + slight shadow increase. Duration: 200ms.

### Transitions
- **Accordion expand/collapse:** 250ms ease-out on grid-template-rows.
- **Chevron rotation:** 200ms on transform: rotate(90deg).
- **Filter chip toggle:** 200ms on background-color + border-color.
- **Stat card active state:** 200ms ring/border appearance.

### Animations
- **Skeleton shimmer:** 1.5s ease-in-out infinite.
- **Overdue pulse:** `animate-pulse` on the tiny dot indicator (Tailwind built-in).
- **Loading spinner:** `animate-spin` (already implemented).

### What NOT to Animate
- Do not animate width/height/top/left (layout-triggering properties).
- Do not add page transition animations (they slow perceived performance).
- Do not add decorative animations that serve no UX purpose.

---

## 7. Accessibility Requirements

- All interactive elements must be keyboard navigable (tab/enter/space).
- Stat card filters: `<button>` elements with `aria-pressed` state.
- Accordion: Use `aria-expanded` on the toggle button.
- Task checkboxes: Use proper `role="checkbox"` and `aria-checked`.
- Focus states: Add `focus-visible` ring (`2px solid accent, 2px offset`) to all interactive elements.
- Color alone must not be the only indicator of state — always pair with text/icon.

---

## 8. Implementation Priority (Phased Approach)

### Phase A: Quick Wins (Biggest Visual Impact, Least Code Change)
1. **Page header upgrade** — Add subtitle, remove bottom border, adjust padding.
2. **Remove task row dividers** — Replace `border-b` with `mx-2 rounded-xl` hover rows.
3. **Stat card icon containers** — Add the colored background containers behind icons.
4. **Increase hover feedback** — Bump card hover to `translateY(-2px)`, task row to `bg-white/[0.03]`.
5. **Chevron rotation animation** — Single icon + rotate instead of icon swap.

### Phase B: Structural Polish
6. **Skeleton loading states** — Replace spinner with layout-mimicking skeletons.
7. **Empty state upgrade** — Icon + friendly text.
8. **Sidebar grouped nav** — Add section labels ("Core" / "Tools").
9. **Sidebar user area** — Add profile section at bottom.
10. **Accordion animation** — Smooth expand/collapse with grid-template-rows.

### Phase C: Advanced Features
11. **Clickable stat card filters** — Toggle task list filtering by clicking stats.
12. **Filter chips** — Status/Project/Due filter chips below search.
13. **Overflow menu on hover** — "..." menu on task rows revealing quick actions.
14. **Keyboard shortcuts** — Tab through stat filters, enter to toggle.

---

## 9. File Change Map

| File | Changes |
|------|---------|
| `globals.css` | Add new tokens, utility classes (shimmer, hover-lift, accordion, focus-ring) |
| `tasks/page.tsx` | New header with title + subtitle, remove border-b bar, adjust padding |
| `TaskTree.tsx` | Update StatCard design, add skeleton loading, add empty state, add filter-by-stat |
| `TaskItem.tsx` | Remove border-b, add rounded hover rows, add group hover menu, slightly larger icons |
| `TaskCategory.tsx` | Remove inner border-t, add accordion animation, chevron rotation |
| `TaskFilters.tsx` | Minor: increase height, add future filter chip placeholders |
| `DueBadge.tsx` | Minor: add tabular-nums, optional pulse dot for overdue |
| `Sidebar.tsx` | Add grouped nav labels, user area at bottom, increase hover opacity |
| `AppShell.tsx` | No changes needed |

---

## 10. Do NOT Do These Things

- **Do not introduce new routes.**
- **Do not add a new global state library** (no Redux, Zustand, etc.).
- **Do not change API calls or data fetching logic.**
- **Do not change the mobile layout** — desktop is priority; mobile should remain usable but is not the focus.
- **Do not add new npm dependencies** unless absolutely necessary (prefer Tailwind utilities).
- **Do not use CSS modules or styled-components** — stay in the Tailwind + CSS variables pattern.
- **Do not pixel-match the OpenClaw screenshots** — match the *vibe, hierarchy, and spacing philosophy*, not exact layouts.
- **Do not over-animate** — subtle transitions only, never flashy.

---

## 11. Visual Checklist (Definition of Done)

When the redesign is complete, verify these statements are true:

- [ ] Page title is visually dominant with a subtitle below it
- [ ] Stat cards have colored icon containers and feel "liftable" on hover
- [ ] Task rows have NO visible divider lines between them
- [ ] Task rows have rounded hover backgrounds
- [ ] Category accordions expand/collapse smoothly (not instant)
- [ ] Chevrons animate rotation (not icon swap)
- [ ] Loading state shows skeleton layout (not a centered spinner)
- [ ] Empty state has an icon and friendly message
- [ ] Sidebar has grouped nav sections with tiny labels
- [ ] All hover states are noticeable but not flashy
- [ ] Typography has clear hierarchy (max 3-4 distinct sizes visible at once)
- [ ] Spacing feels generous — not cramped, not wasteful
- [ ] The overall vibe reads "calm command center" not "spreadsheet"

---

## Appendix A: Quick Reference Color Map

```
Background layers (dark → light):
  #080a10 → #0d1017 → #111520 → #141925 → #1a2033

Status colors:
  Active:    #4F8EF7 (accent blue)     bg: rgba(79,142,247,0.12)
  Overdue:   #F87171 (danger red)      bg: rgba(248,113,113,0.12)
  Due Today: #FBBF24 (warning yellow)  bg: rgba(251,191,36,0.12)
  Completed: #34D399 (success green)   bg: rgba(52,211,153,0.12)
  Info:      #A78BFA (purple)          bg: rgba(167,139,250,0.12)

Text hierarchy:
  Primary:   #E8ECF4
  Secondary: #8B95AE
  Tertiary:  #5C6580
```

## Appendix B: Reference CSS for Key Patterns

### Glassmorphism Card (already exists — reference)
```css
.glass-card {
  background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%),
              var(--color-card);
  border: 1px solid var(--color-border);
  box-shadow:
    0 2px 4px rgba(0, 0, 0, 0.2),
    0 8px 24px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  border-radius: 16px;
}
```

### Glow Effect Behind Card
```css
.glow-accent {
  box-shadow:
    0 2px 4px rgba(0, 0, 0, 0.2),
    0 8px 24px rgba(0, 0, 0, 0.15),
    0 0 24px rgba(79, 142, 247, 0.08);
}
```

### Status Indicator with Pulse
```css
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  animation: pulse 2s ease-in-out infinite;
}
.status-dot.active { background: var(--color-success); box-shadow: 0 0 6px var(--color-success); }
.status-dot.warning { background: var(--color-warning); box-shadow: 0 0 6px var(--color-warning); }
.status-dot.danger { background: var(--color-danger); box-shadow: 0 0 6px var(--color-danger); }
```
