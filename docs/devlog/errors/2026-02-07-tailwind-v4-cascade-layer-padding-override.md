# Error: Tailwind v4 CSS Cascade Layer Padding Override

**Date:** 2026-02-07
**Severity:** High
**Component:** Frontend layout (globals.css, AppShell, Sidebar)

## Symptoms

- All page content was flush against the sidebar edge with no visible gap/padding
- Right-side content (DueBadge text like "1d overdue", "No date", "Today") was clipped at the viewport edge
- Section headers appeared to have slight top clipping near card borders
- Adding `md:px-6` padding to `<main>` in AppShell had no visible effect despite the class being present in both the source code and rendered HTML

## Root Cause

**Three compounding issues:**

### 1. Unlayered CSS reset overriding Tailwind v4 utilities (PRIMARY)

In `globals.css`, a manual CSS reset was placed OUTSIDE any `@layer` block:

```css
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
```

In Tailwind v4, ALL utilities are generated inside `@layer utilities`. In CSS Cascade Layers, **unlayered styles ALWAYS have higher priority than layered styles**, regardless of specificity. This meant the unlayered `* { padding: 0 }` was overriding Tailwind padding utilities like `md:px-6`, `px-8`, etc.

The reset was also completely redundant — Tailwind v4 already provides the identical reset inside `@layer base`:

```css
@layer base {
  *, :after, :before {
    box-sizing: border-box;
    border: 0 solid;
    margin: 0;
    padding: 0;
  }
}
```

The layered version works correctly (utilities override base). The unlayered duplicate broke the cascade.

### 2. Sidebar missing `flex-shrink: 0`

The sidebar `<aside>` had `w-60` (240px) but no `shrink-0`. In flexbox, items default to `flex-shrink: 1`, meaning the sidebar could be compressed below 240px by the main content area.

### 3. Main content missing `min-width: 0`

The `<main>` element had `flex-1` but no `min-w-0`. Without it, a flex child defaults to `min-width: auto`, preventing it from shrinking below its content's intrinsic width. This caused content to overflow the available space, which was then clipped by `overflow-hidden`.

## Fix Applied

1. **Removed the unlayered `* { ... }` reset from `globals.css`** — Tailwind's `@layer base` already provides it, so the duplicate was purely harmful
2. **Added `shrink-0` to the sidebar** in `Sidebar.tsx` — prevents the sidebar from being squeezed by flex layout
3. **Added `min-w-0` to `<main>`** in `AppShell.tsx` — allows the main content to properly constrain its children

## Files Modified

- `frontend/src/app/globals.css` — Removed unlayered `* { box-sizing; margin; padding }` reset (lines 47-51)
- `frontend/src/components/layout/Sidebar.tsx` — Added `shrink-0` to `<aside>` className
- `frontend/src/components/layout/AppShell.tsx` — Added `min-w-0` to `<main>` className

## How to Prevent

- **Never put custom CSS outside `@layer` blocks when using Tailwind v4.** All custom styles should go in `@layer base`, `@layer components`, or `@layer utilities`. Unlayered CSS will override Tailwind utilities.
- **Always add `shrink-0` to fixed-width sidebar elements** in flex layouts — this is a standard flex pattern.
- **Always add `min-w-0` to `flex-1` content areas** — this prevents the flex overflow bug where content pushes the container wider than available space.
- Reference: This is a documented Tailwind v4 migration gotcha. Tailwind v3 didn't use CSS Cascade Layers, so unlayered resets worked fine. Tailwind v4 moved to layers, making unlayered custom CSS a silent override.

## Lessons Learned

- **CSS Cascade Layers change the game.** The old pattern of `* { margin: 0; padding: 0; }` at the top of a stylesheet is actively harmful in Tailwind v4. It silently overrides utility classes because unlayered styles beat layered styles regardless of specificity.
- **The fix appeared to already be applied but wasn't working.** Another debugging session correctly identified that `<main>` needed padding and added `md:px-6`. The class was present in the source AND in the rendered HTML AND in the generated CSS. But the unlayered reset was overriding it at the cascade level — a deeply non-obvious failure mode.
- **When a CSS class is present but has no effect, check cascade layers.** DevTools will show the property being overridden, but the "why" requires understanding the layer hierarchy.
- **Tailwind v4's base layer is comprehensive.** Don't duplicate its resets — you'll only cause cascade conflicts.

## Detection

- Discovered visually: content was flush against the sidebar with no gap, and right-edge badges were clipped
- Confirmed by inspecting the generated CSS: `@layer utilities` closed at line 2181, then the unlayered `* { padding: 0 }` appeared at line 2183
- A previous debugging session tried to fix the symptoms (adding padding classes) without discovering the cascade layer root cause
- Earlier detection: a CSS linter rule that warns about unlayered styles when using Tailwind v4 would catch this instantly
