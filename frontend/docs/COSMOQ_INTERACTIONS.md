# Cosmoq interaction extraction

Source: https://cosmoq.framer.website/ (Framer-published site). Extracted via Playwright —
computed styles, mutation-observed inline style changes, and real pointer input — on
2026-07-18. This documents behavior only (triggers, timing, easing, before/after state),
not copied text or imagery. Used to inform motion choices in this project's existing
Framer Motion setup (`motion/react`), not to rebuild the site.

## Page topology (for reference)

Single scroll page, 12 sections top to bottom: Hero → Highlighted Text → Exceptionalities
→ Features → Products → Steps → Data & Privacy → Testimonial → Pricing → FAQ → (decorative
background-gradient layer) → Integration. No scroll-snap, no smooth-scroll library (checked
for Lenis/Locomotive — absent, native scroll only).

## 1. Load-in entrance animation (confirmed, primary finding)

**Interaction model:** time/mount-driven, not scroll-driven for above-the-fold content —
it fires once, staggered, starting ~300–550ms after navigation. (Below-the-fold sections
were already fully settled by the time they entered the viewport in every test, which is
consistent with either a very early IntersectionObserver trigger margin or an eager
one-shot appear — practically, treat it as "animates in shortly after the page/section is
reachable," not something a user will see trigger mid-scroll.)

**Mechanism:** each animated node carries a `data-framer-appear-id` and is driven by inline
`style` mutations (opacity + transform), not CSS `@keyframes` or `:hover`. Only one CSS
keyframe exists site-wide, an unrelated loading-spinner rotation.

**Curve shape:** NOT a fixed-duration cubic-bezier. Sampling the intermediate transform
values shows exponential decay toward the resting value with no overshoot — i.e. a
critically/over-damped spring, not an `ease-out` timing function. Settle time ~0.6–0.8s of
perceived motion (observed capture window was inflated by instrumentation overhead).

**States observed, by element role:**

| Role | Before (initial) | After (resting) |
|---|---|---|
| Hero title | `opacity: 0` (technically `0.001`), `translateY(80px) scale(0.9)` | `opacity: 1`, `transform: none` |
| Small label/eyebrow text | `opacity: 0` | `opacity: 1`, no transform offset |
| Decorative glow/"frost" shapes | `opacity: 0`, `translateY(80px)` | `opacity: 1`, `transform: none` |
| Background gradient layer | `opacity: 0`, `translateY(-50px)` (slides down *into* place, opposite direction from foreground content) | `opacity: 1`, `transform: none` |
| Hero dashboard/product mockup image | `opacity: 0`, `translateY(40px)` | (same shape, smaller offset, no scale) |

Pattern: foreground content/headings slide up + scale in; decorative background elements
slide down into place; small text-only elements just fade, no positional offset. Elements
are staggered by role rather than sharing one synchronized timestamp.

## 2. Primary CTA — the pill button glow

**Interaction model:** static, not hover-driven. Confirmed by dispatching real pointer
input (Playwright `mouse.move` + `locator.hover()`, not synthetic events) at the nav "Get
Started" button and diffing `box-shadow`, `filter`, `transform` before/after — all
identical. The signature dual-tone inset glow is an always-on box-shadow, not a
`whileHover` effect:

```
box-shadow:
  0 0.83px 0.83px -0.75px rgba(0,0,0,.18),
  0 2.26px 2.26px -1.5px rgba(0,0,0,.18),
  0 4.96px 4.96px -2.25px rgba(0,0,0,.17),
  0 11.01px 11.01px -3px rgba(0,0,0,.14),
  0 28px 28px -3.75px rgba(0,0,0,.06),
  inset -4px 3px 9px rgb(1,117,255),   /* blue light source, top-right */
  inset 3px -2px 8px rgb(255,205,125); /* gold light source, bottom-left */
```

This project's `.cosmoq-pill` in `globals.css` already reproduces this near-exactly — no
change needed there.

**No CSS `:hover` rules found** controlling any component chrome — the only `:hover` rules
in the site's stylesheet are generic Framer link-text color inheritance (a framework
default, unrelated to buttons/cards). Any hover motion on this site (if present elsewhere)
runs through Framer Motion's `whileHover` prop, applied per-component, not through
stylesheet rules — so it can't be harvested from CSS alone, only from live interaction, and
none was found on the elements tested (primary CTA, first Products-section child probed).

## 3. Header

**Fixed**, `top: 0`, height ~85px, transparent background. **Confirmed no scroll-driven
change** — compared computed `background-color`, `backdrop-filter`, `box-shadow`, `height`
at `scrollY: 0` vs `scrollY: 900`: identical in every property checked. No shrink, no blur,
no border-on-scroll. Treat this as a deliberate negative finding, not a gap in extraction —
don't invent a "sticky header transition" that isn't there.

## 4. What was checked and found absent

- Smooth-scroll library (Lenis/Locomotive): absent.
- Scroll-snap: absent.
- Scroll-driven header transition: absent (see §3).
- CSS-hover-driven component states: absent (only generic link-color rules).
- Scroll-triggered re-animation while scrolling past a section mid-page: not observed in
  testing — sections were already in their resting state by the time they were reachable.

## Recommendations for this project (adaptation, not verbatim reuse)

The existing pages (`page.tsx`, `study/baseline/page.tsx`, `study/multiagent/page.tsx`)
already use `motion/react` with a stagger-on-mount pattern (`staggerContainer` /
`staggerItem`), but drive it with a fixed-duration cubic-bezier (`EASE_OUT = [0.16, 1, 0.3,
1]`). Swapping the top-level entrance transitions to a spring (no bounce, critically
damped) gets the same "settles into place" feel Cosmoq uses, without copying its exact
component tree or content. Concretely: entrance-only, kept to the existing stagger/reveal
variants:

- Hero header block: fade + slight upward slide, spring settle.
- Card grid / stagger items: fade + upward slide, spring settle, staggered per item
  (already staggered — just change the transition type).
- No change to hover states (already correct/static per §2), no scroll-driven header
  (per §3, none exists to add), no smooth-scroll (per §4).
