# DESIGN.md — SitePilot visual system

## Theme

Light, high-contrast "precision instrument" UI. Content-first (Apple HIG
clarity/deference/depth): quiet neutral surfaces, deep graphite ink, one
committed petrol-blue accent, translucent app chrome, soft layered elevation.

## Color (OKLCH; strategy: Restrained — tinted neutrals + one accent ≤10%)

| Token | Value | Use |
|---|---|---|
| `--bg` | `oklch(0.972 0.004 230)` | App canvas (cool-tinted near-white, tinted toward accent hue) |
| `--surface` | `oklch(1 0 0)` | Panels, tables, dialogs |
| `--surface-2` | `oklch(0.958 0.006 230)` | Table heads, wells, input bg |
| `--ink` | `oklch(0.22 0.02 240)` | Primary text (≈13.5:1 on surface) |
| `--ink-2` | `oklch(0.42 0.02 240)` | Secondary text (≈7:1) |
| `--ink-3` | `oklch(0.50 0.02 240)` | Captions/meta, still ≥4.5:1 |
| `--accent` | `oklch(0.49 0.105 220)` | Primary buttons, active nav, selection, links |
| `--accent-strong` | `oklch(0.42 0.105 220)` | Hover/pressed |
| `--accent-tint` | `oklch(0.94 0.02 220)` | Selected/active fills |
| `--ok` | `oklch(0.52 0.12 155)` | Success states |
| `--warn` | `oklch(0.55 0.12 80)` | Warnings, pending |
| `--bad` | `oklch(0.52 0.19 25)` | Errors, overdue |
| `--line` | `oklch(0.90 0.006 230)` | Hairline borders |

Semantic status colors appear only as state (badges, alerts, deltas), never as
decoration. No warm-cream neutrals.

## Typography

System stack: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI Variable", "Segoe UI", Roboto, Inter, sans-serif`.
One family, weights 400/500/600/700. Fixed rem scale (ratio ≈1.2):
12 · 13 · **14 (base)** · 16 · 19 · 23 · 28 · 34. Login display 40px/700/-0.02em.
Headings: 600, letter-spacing -0.01em, `text-wrap: balance`.
Numbers in tables/KPIs: `font-variant-numeric: tabular-nums`.

## Elevation & shape

- Radii: control 10px · card 16px · dialog 20px · pill 999px (primary buttons).
- Shadows (layered, cool): `--shadow-1` hairline+2px; `--shadow-2` 8/24px at
  6-8% for cards; `--shadow-3` 24/64px for dialogs/popovers.
- App chrome (topbar) is translucent: `backdrop-filter: blur(20px) saturate(1.6)`
  over `oklch(1 0 0 / 0.72)` — the one deliberate glass surface.

## Motion

Tokens: `--ease-out: cubic-bezier(0.22,1,0.36,1)` (quint), `--ease-out-expo:
cubic-bezier(0.16,1,0.3,1)`; durations 120/200/320/560ms; exits ≈75% of enter.
- Route/tab change: content crossfade + 6px rise, 320ms.
- Dialogs: backdrop fade + panel scale 0.97→1 rise, 320ms in / 200ms out.
- Tables/lists: sibling stagger ≤40ms/row, capped at 10 rows (400ms total).
- KPIs: count-up 700ms expo; progress bars fill from 0 on first paint.
- Feedback: buttons press to scale(0.97) 120ms; inputs focus ring 200ms.
- Loading: shimmer skeletons, never centered spinners.
- Full `prefers-reduced-motion: reduce` block: transitions/animations collapse
  to near-instant crossfades.

## Iconography & imagery

Inline SVG icon set, 20px grid, 1.6px stroke, round caps (no emoji in chrome).
Illustrations are hand-authored geometric SVGs in brand colors (login hero,
empty states) — zero third-party/copyrighted assets. Landing page photography
is Unsplash (free license), verified to resolve before shipping.

## Components

Buttons (pill primary / soft-outline secondary / ghost / destructive), inputs
with focus rings, tables (sticky heads, hover wash, staggered entrance), badges
(tinted pills), KPI tiles (varied, not identical card grids), tabs with animated
underline, dialog forms, toasts (bottom-right slide), skeletons, empty states
with illustration + next-step hint, comment threads, notification list.
