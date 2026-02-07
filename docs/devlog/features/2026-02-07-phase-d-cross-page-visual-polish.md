# Feature: Phase D — Cross-Page Visual Polish

**Date:** 2026-02-07
**Branch:** main

## Summary

Applied consistent visual treatment across all pages of the Brent OS frontend. Key changes include a sidebar with colored navigation icons and a distinct opaque background, fixed chat text wrapping and hyphen-mangling bugs, upgraded assistant message bubble styling, and per-color active tabs in the mobile navigation bar.

## Problem / Motivation

After Phases A–C polished the Tasks page with interactive features and structural improvements, the rest of the UI had inconsistencies: the sidebar used a semi-transparent blurred background that blended into the content area, all nav icons were monochrome gray regardless of route, the chat page had text wrapping issues on mobile (long messages overflowed horizontally), and the `normalizeContent()` function aggressively stripped spaces around ALL hyphens — mangling em dashes, number ranges, and producing garbled text like "5– 4. 0 car ats". The assistant message bubble was also nearly invisible (`bg-white/[0.02]`).

## Solution

Four files modified with surgical changes:

1. **globals.css** — Added `--color-sidebar` token, `.markdown-content` word-wrap rules, and `max-width: 100%` on `pre` blocks to constrain code blocks within their container.

2. **Sidebar.tsx** — Introduced a static `NAV_COLORS` map assigning each route a color theme (Chat=accent/blue, Tasks=success/green, Calendar=warning/amber, Insights=purple). Inactive icons show their color at 60% opacity. Active state uses colored background, border, glow, and icon highlight. Sidebar background switched from `bg-surface/90 backdrop-blur-xl` to opaque `bg-sidebar`.

3. **MobileNav.tsx** — Each tab entry now carries its own `color` and `glow` strings. Active tab uses its assigned color instead of the previous all-blue treatment.

4. **ChatMessage.tsx** — Fixed `normalizeContent()` regex from `/ -/g` and `/- /g` (which stripped ALL spaces around hyphens) to `(\w) - (\w)` → `$1-$2` (only collapses compound-word patterns). Added `break-words` to user message `<p>` tag. Upgraded assistant bubble from `bg-white/[0.02]` to `bg-surface` for visible but recessive styling.

## Files Modified

**CSS tokens & global styles:**
- `frontend/src/app/globals.css` — sidebar color token, markdown word-wrap, pre max-width

**Layout components:**
- `frontend/src/components/layout/Sidebar.tsx` — colored nav icons, opaque background, spacing tweaks
- `frontend/src/components/layout/MobileNav.tsx` — per-tab color and glow

**Chat components:**
- `frontend/src/components/chat/ChatMessage.tsx` — hyphen regex fix, user text wrapping, assistant bubble upgrade

## Key Decisions & Trade-offs

- **Static color map with literal Tailwind classes**: The `NAV_COLORS` object uses full string literals (e.g., `"text-accent/60"`) rather than computed class names. This is intentional — Tailwind's purge/JIT compiler needs to see complete class strings to include them in the build output. Dynamic string interpolation like `text-${color}/60` would be silently dropped.

- **Opaque sidebar vs blur**: Switched from `bg-surface/90 backdrop-blur-xl` to a dedicated opaque `--color-sidebar: #0f1219` token. The blur was computationally expensive and didn't provide meaningful visual benefit since the sidebar content rarely overlaps dynamic backgrounds. The opaque darker tone creates a clearer visual boundary.

- **Compound-word regex only**: The hyphen fix uses `(\w) - (\w)` which only matches word characters on both sides. This preserves em dashes (`—`), list items starting with `- `, and number ranges while still fixing streaming artifacts like `real - time` → `real-time`.

- **No color hint for inactive mobile icons**: Mobile nav keeps inactive tabs as `text-text-dim` without color tinting. On the small mobile bar, colored hints for every tab would be too noisy — color is reserved for the active selection only.

## Patterns Established

- **`NAV_COLORS` pattern**: Static color maps with pre-built Tailwind class strings for per-route theming. Future nav items should add an entry to this map.
- **`--color-sidebar` token**: Dedicated sidebar background separate from `--color-surface`. Any sidebar-like chrome should use this token.
- **`.markdown-content` word-wrap**: All markdown-rendered content now inherits word-break rules from globals.css — no need to add per-component overflow handling.

## Testing

- `npx next build` compiles cleanly with no errors
- Dev server returns HTTP 200 after restart
- Visual verification checklist:
  - Sidebar has distinct darker background vs main content area
  - Each nav icon shows its assigned color (blue/green/amber/purple)
  - Active nav item has colored bg, border, icon glow
  - Mobile bottom nav: active tab uses its assigned color
  - Chat: long user messages wrap correctly (no horizontal scroll)
  - Chat: assistant responses render without garbled hyphens
  - Chat: assistant bubble is visibly distinct from background
  - Calendar/Insights pages render correctly with updated tokens

## Future Considerations

- The color map is hardcoded per-route. If routes become dynamic or user-configurable, this would need to pull from a central theme config.
- The `normalizeContent()` function still applies broad punctuation-space fixes that could theoretically affect intentional formatting in code blocks — but since ReactMarkdown handles code blocks separately, this is low risk.
- Consider adding subtle hover color transitions to inactive sidebar icons for additional interactivity feedback.
