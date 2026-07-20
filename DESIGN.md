---
name: Secure Coding Study
description: Dark, layered UI for an unsupervised HITL secure-coding research task. Three token layers — global base, OLED elevation, and two page-scoped accent systems.
extractedFrom:
  - frontend/app/globals.css
  - frontend/app/page.tsx
extractedAt: 2026-07-18
colors:
  base:
    canvas: "#030712"
    surface: "#111827"
    surface-raised: "#1f2937"
    border: "#1f2937"
    border-strong: "#374151"
    ink: "#f3f4f6"
    ink-secondary: "#d1d5db"
    ink-muted: "#9ca3af"
    ink-faint: "#6b7280"
    signal: "#3b82f6"
    signal-deep: "#2563eb"
    signal-bright: "#60a5fa"
    success: "#16a34a"
    success-deep: "#15803d"
    success-surface: "#052e16"
    success-ink: "#86efac"
    danger-surface: "#450a0a"
    danger-border: "#991b1b"
    danger-ink: "#f87171"
    warning-surface: "#422006"
    warning-border: "#854d0e"
    warning-ink: "#facc15"
  oled:
    oled: "#000000"
    oled-1: "#0a0a0d"
    oled-2: "#101116"
    oled-3: "#17181f"
    oled-4: "#1e1f28"
    hairline: "rgba(255,255,255,0.07)"
    hairline-strong: "rgba(255,255,255,0.14)"
    hairline-top: "rgba(255,255,255,0.05)"
  ai-accent:
    ai: "#8b5cf6"
    ai-bright: "#a78bfa"
    ai-deep: "#6d28d9"
    ai-surface: "rgba(139,92,246,0.08)"
    ai-border: "rgba(139,92,246,0.28)"
  cosmoq-accent:
    cosmoq-blue: "#0175ff"
    cosmoq-blue-bright: "#7da4ff"
    cosmoq-blue-tint: "rgba(125,164,255,0.16)"
    cosmoq-gold: "#ffcd7d"
    cosmoq-amber: "#ffb349"
typography:
  fontFamily:
    sans: "var(--font-geist-sans)"
    mono: "var(--font-geist-mono)"
  scale:
    display-h1: { size: "40px / 48px (sm)", weight: 500, lineHeight: 1.2, tracking: "-1.2px / -1.44px (sm)" }
    h2-card-title: { size: "20px", weight: 500, lineHeight: "tight", tracking: "-0.4px" }
    body-lead: { size: "16px", weight: 400, lineHeight: 1.625, tracking: "-0.48px" }
    body: { size: "14px", weight: 400, lineHeight: 1.4-1.625 }
    body-sm: { size: "13px", weight: 400, lineHeight: 1.625 }
    label-eyebrow: { size: "11px", weight: 600, lineHeight: "normal", tracking: "wide", transform: "uppercase" }
    badge: { size: "10px", weight: 600, tracking: "wide", transform: "uppercase" }
    caption: { size: "12px", weight: 400 }
    mono-index: { size: "12px", weight: 400, family: "mono" }
spacing:
  scale: [4, 8, 10, 12, 14, 16, 20, 24, 40, 64, 80]
  unit: "4px base, 8px emphasis rhythm"
radius:
  pill: "9999px (rounded-full) — buttons, badges, chips, dot indicators"
  card-cosmoq: "24px — .cosmoq-card / .cosmoq-card-accent (home page)"
  card-oled-generic: "12–16px (rounded-xl/rounded-2xl, applied per instance) — .elevate-* system"
  nested-box: "16px (rounded-2xl) — inputs, inner detail boxes"
  skeleton: "6px (rounded-md)"
  circle: "50% — avatars/dot indicators"
elevation:
  oled-system: ["elevate-1", "elevate-2", "elevate-3", "elevate-glass", "elevate-critical", "elevate-high", "elevate-medium", "elevate-low"]
  cosmoq-system: ["cosmoq-card", "cosmoq-card-accent", "cosmoq-pill", "cosmoq-pill-ghost"]
motion:
  ease-out-custom: "cubic-bezier(0.16, 1, 0.3, 1)"
  durations:
    entrance: "0.36s (stagger item), 0.4s (header/shake)"
    reveal: "0.22s in / 0.14s out"
    hover: "0.18s"
    button-transition: "0.15s"
    loop-skeleton: "1.6s"
    loop-stage-pulse: "1.8s"
    loop-ambient-drift: "26s"
  stagger: "staggerChildren 0.06s, delayChildren 0.05s"
  press-scale: "0.97"
  hover-lift: "-2px (y)"
breakpoints:
  sm: "640px"
  md: "768px"
---

# Design System: Secure Coding Study

## 1. Overview

This system is built from **four layers**, most-general to most-specific. The other three are opt-in and scoped by class/page, so adding a layer to one page never changes another.

| Layer | Scope | Activated by |
|---|---|---|
| **Base** | Shared token set; no page currently renders on it alone | Plain CSS vars, no wrapper class |
| **OLED** | Every study page | `.oled-scope` wrapper — home page, baseline study page, multi-agent study page |
| **AI-violet accent** | Multi-agent pipeline UI only | `.elevate-3`, `bg-ai-*`, `text-ai-*` classes inside `.oled-scope` |
| **Cosmoq accent** | Home page + baseline study page | `.cosmoq-card*`, `.cosmoq-pill*`, `bg/text/border-cosmoq-*` classes inside `.oled-scope` |

**As of this revision, all three study pages share the OLED foundation.** Condition-neutrality between baseline and multi-agent is now expressed through the *accent layer* (Cosmoq blue/gold on baseline vs. AI-violet on multi-agent), not through one condition being flat/plain and the other richly styled — both get the same card system, radius, elevation, and motion vocabulary; only the accent hue differs.

**Why layered instead of one flat palette:** the study has two experimental conditions (baseline vs. multi-agent) that must never visually cue which one is "more advanced," per the study's validity requirements. Earlier revisions of this system tried to enforce that by keeping baseline on a separate, plainer palette — but that produced the opposite problem: multi-agent's OLED/glow treatment made it look more polished by construction, which is itself a confound. The current approach instead gives every study page the same OLED foundation, card system, radius, elevation, and motion vocabulary, and reserves *only the accent hue* (Cosmoq blue/gold vs. AI-violet) to distinguish conditions — matched visual weight, different color story.

**Baseline study page** now runs on `.oled-scope` + the Cosmoq accent layer (same `.cosmoq-card`/`.cosmoq-pill*` classes and type scale as the home page). The old flat **Base** layer (`#030712` canvas, `#111827` cards, Signal Blue `#3b82f6`) is retained in this token set for reference but is no longer rendered by any live page — reintroduce it only if a future page deliberately needs a lower-visual-weight treatment, not as a per-condition default.

## 2. Colors

### Base layer (shared primitives, not currently used by any live page)
| Token | Value | Usage |
|---|---|---|
| `canvas` | `#030712` | Page background (non-OLED pages) |
| `surface` | `#111827` | Card background |
| `surface-raised` | `#1f2937` | Inputs, nested content blocks |
| `border` | `#1f2937` | Card borders |
| `border-strong` | `#374151` | Input borders, emphasized dividers |
| `ink` | `#f3f4f6` | Primary text |
| `ink-secondary` | `#d1d5db` | Body copy inside cards |
| `ink-muted` | `#9ca3af` | Secondary/descriptive text |
| `ink-faint` | `#6b7280` | Labels, placeholders, timestamps |
| `signal` / `signal-deep` / `signal-bright` | `#3b82f6` / `#2563eb` / `#60a5fa` | The one accent on the base layer — primary CTAs, focus rings |
| `success` family | `#16a34a`, `#15803d`, `#052e16`, `#86efac` | Advance/complete actions and verdicts |
| `danger` family | `#450a0a`, `#991b1b`, `#f87171` | Errors, failed verdicts |
| `warning` family | `#422006`, `#854d0e`, `#facc15` | Mid-task nudges, non-fatal callouts |

### OLED layer (`.oled-scope`)
| Token | Value | Usage |
|---|---|---|
| `oled` | `#000000` | True-black canvas |
| `oled-1` … `oled-4` | `#0a0a0d` → `#1e1f28` | Elevation steps — each level one shade lighter |
| `hairline` / `hairline-strong` / `hairline-top` | `rgba(255,255,255,.07/.14/.05)` | Borders and inset top-edge highlight (depth without shadows being invisible on true black) |

### AI-violet accent (multi-agent page only)
| Token | Value | Usage |
|---|---|---|
| `ai` / `ai-bright` / `ai-deep` | `#8b5cf6` / `#a78bfa` / `#6d28d9` | Agent/pipeline-specific highlights, hint UI |
| `ai-surface` / `ai-border` | `rgba(139,92,246,.08/.28)` | Tinted backgrounds and borders for AI-generated content |

### Cosmoq accent (home page + baseline study page)
| Token | Value | Usage |
|---|---|---|
| `cosmoq-blue` / `cosmoq-blue-bright` | `#0175ff` / `#7da4ff` | Header dot, focus rings, pipeline-step dots, badge text |
| `cosmoq-blue-tint` | `rgba(125,164,255,.16)` | Badge background wash |
| `cosmoq-gold` / `cosmoq-amber` | `#ffcd7d` / `#ffb349` | Glow-only — never a flat fill; appears solely in the `.cosmoq-pill` dual-tone inset glow |

**Rule carried over from the original system:** severity/status must never be color-only — every status/severity token is always paired with a text label or icon.

## 3. Typography

**Fonts:** Geist (sans, headings/body) and Geist Mono (code, IDs, timers) via `--font-sans`/`--font-mono`. No other families in use.

| Role | Size | Weight | Line-height | Tracking | Example use |
|---|---|---|---|---|---|
| Display H1 | 40px → 48px (`sm:`) | 500 | 1.2 | −1.2px → −1.44px (`sm:`) | Page title |
| Card title (H2) | 20px | 500 | tight | −0.4px | "Baseline" / "Multi-Agent" |
| Body-lead | 16px | 400 | 1.625 | −0.48px | Header subhead paragraph |
| Body | 14px | 400 | 1.4–1.625 | — | Task list items, card descriptions, button labels |
| Body-sm | 13px | 400 | 1.625 | — | Fact-list items |
| Label / eyebrow | 11px | 600 | normal | wide, uppercase | "Participant ID", "Task Queue", top badge |
| Badge | 10px | 600 | normal | wide, uppercase | "Control" / "Experimental" |
| Caption | 12px | 400 | normal | — | Footer note, error text |
| Mono index | 12px | 400 (mono) | normal | — | "01" / "02" task numbers |

**Max weight in use is 500 (medium)** — no bold (700) headings anywhere in the current pages. This is a deliberate departure from the original flat system (which used 700-weight titles); keep new pages at ≤600 weight to stay consistent with the current type voice.

## 4. Spacing

Core values in active use: `4, 8, 10, 12, 14, 16, 20, 24, 40, 64, 80` (px). Base unit is 4px with an 8px emphasis rhythm — most gaps/padding land on 8/16/24; 10, 14, 20, 40 appear as intentional half-steps at input padding, list gaps, and section margins.

| Context | Value |
|---|---|
| Section/card internal padding | 24px (`p-6`) |
| Nested box padding | 16px (`p-4`) |
| Page horizontal padding | 24px (`px-6`) |
| Page vertical padding | 64px → 80px (`sm:`) |
| Card-to-card gap | 24px (`gap-6`) |
| Grid gap (condition cards) | 16px (`gap-4`) |
| List item gap | 8–10px (`gap-2` / `gap-2.5`) |
| Header-to-body margin | 40px (`mb-10`) |

**Content widths:** `860px` (page column), `560px` (header text), `480px` (subhead paragraph) — reuse these for any new page built on the same column.

## 5. Border radius

| Value | Usage |
|---|---|
| `9999px` (pill) | Buttons, badges, chips, dot indicators |
| `24px` | `.cosmoq-card` / `.cosmoq-card-accent` — home-page cards |
| `12–16px` | `.elevate-*` cards elsewhere (radius applied per-instance via `rounded-xl`/`rounded-2xl`, not baked into the class) |
| `16px` | Nested/inner boxes, text inputs |
| `6px` | Skeleton loading bars |
| `50%` | Circular avatars/dots |

No sharp corners anywhere in the current system.

## 6. Elevation / shadow

Two parallel systems, both additive and non-conflicting — pick the one matching your page's scope.

**OLED system** (`.elevate-1/2/3/glass/critical/high/medium/low`) — depth via lightness steps + hairline border + a subtle inset top-highlight, escalating outer shadow size, and (for `elevate-3` and severity variants) a matched-hue glow. Used on the multi-agent page.

**Cosmoq system** (home page only):
- `.cosmoq-card` — 24px radius, 5% white inset rim, 5-layer soft outer shadow (sub-px→28px blur, 18%→6% opacity)
- `.cosmoq-card-accent` — same, with a blue-tinted border, 7% inset rim, and an added 24px amber glow (12% opacity) for the "experimental" card
- `.cosmoq-pill` — the signature effect: same 5-layer outer shadow plus a **dual-tone inset glow** (`rgba(1,117,255,.9)` upper-left, `rgba(255,205,125,.85)` lower-right) simulating a light source hitting glass — reserve for the single primary CTA per screen
- `.cosmoq-pill-ghost` — a single 1px inset hairline-strong ring, for secondary actions

## 7. Motion

**Custom easing** (used everywhere, both in Framer Motion and CSS keyframes): `cubic-bezier(0.16, 1, 0.3, 1)` — ease-out with real punch, not the default CSS ease.

| Motion | Duration | Notes |
|---|---|---|
| Section/card entrance | 0.36s | Opacity 0→1, y +14px→0, scale 0.99→1 |
| Header entrance | 0.4s | y −8px→0 |
| List item entrance | 0.28s | x −6px→0, staggered |
| Reveal in / out | 0.22s / 0.14s | Error messages, inline reveals — exit faster than enter |
| Hover lift | 0.18s | Card y −2px |
| Button color/transform transition | 0.15s | Includes `active:scale-[0.97]` press feedback |
| Error shake | 0.4s | `x: [0, -8, 8, -6, 6, -3, 3, 0]` |
| Skeleton pulse (loop) | 1.6s | `ease-in-out infinite` |
| Stage pulse (loop, multi-agent) | 1.8s | `ease-out infinite` |
| Ambient drift (loop, multi-agent only) | 26s | `ease-in-out infinite alternate` |

**Stagger:** `staggerChildren: 0.06s`, `delayChildren: 0.05s` for card sections; list items use `index * 0.05s`.

**Reduced motion:** `globals.css` disables `.oled-ambient`, `.stage-pulse`, and `.check-pop` under `prefers-reduced-motion: reduce`, and freezes `.skeleton` to a static 0.6 opacity. **Gap to fix:** the Framer Motion entrance/stagger animations in `page.tsx` are not currently gated by `prefers-reduced-motion` — wrap future motion-heavy pages with `useReducedMotion()` from `motion/react` before shipping.

## 8. Breakpoints

`sm: 640px`, `md: 768px` (Tailwind defaults) — the only two in active use. `sm` steps up hero type size; `md` switches the condition grid from 1 to 2 columns and the participant-ID row from stacked to inline.

## 9. Do's and Don'ts

- **Do** keep baseline and multi-agent on the same OLED foundation, card system, and type scale — differentiate conditions only through the accent layer (Cosmoq vs. AI-violet), never through overall polish level.
- **Do** scope any new accent color to a new page-specific class/token set (like `cosmoq-*`) rather than overriding the shared `signal`/`ai` tokens other pages depend on.
- **Do** reuse the `cubic-bezier(0.16, 1, 0.3, 1)` ease and the duration table above for any new motion — it's the one consistent "feel" across the app.
- **Do** cap heading weight at 500–600; nothing in the current system uses true bold.
- **Do** gate new Framer Motion entrance animations behind `useReducedMotion()` — the baseline page (`app/study/baseline/page.tsx`) is the current reference implementation for this.
- **Don't** add a fifth color layer without a clear scoping story (which pages, which class) — the four-layer structure only works if each layer stays additive.
- **Don't** reuse `.cosmoq-pill`'s dual-tone glow for more than one CTA per screen — it's a signature/primary-action effect, not a general button style.
- **Don't** resurrect the Base layer as a per-condition default — it exists in this token set for reference only; every current study page runs on OLED.
