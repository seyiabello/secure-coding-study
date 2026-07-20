# Product

## Register

product

## Users

CS/SE students at the University of Exeter (~56 participants) taking part in an MSc research study (COMM514). Each participant works alone, remotely, on their own machine and schedule — no researcher present to clarify anything mid-session. They complete 4 programming tasks under one of two conditions: a baseline AI assistant, or a multi-agent HITL pipeline where the "Code Generator" acts as a mentor (4-level hint ladder, annotation gate, prediction gate, confidence rating) rather than a code-writer. The job to be done is: understand the task, write secure code themselves (with or without AI assistance depending on condition), and complete study instrumentation (annotations, predictions, confidence ratings) accurately. Sessions run 30–60+ minutes per task set.

## Product Purpose

A controlled research instrument, not a product. It exists to let a human-orchestrated multi-agent architecture be compared against a single-agent baseline for secure code generation, without the interface itself introducing a confound. Success looks like: participants complete tasks with full engagement (not rubber-stamping AI output), the two conditions feel equally credible and equally effortful to use, and every interaction the researchers need to measure (hints requested, annotations, predictions, confidence, timing) is captured cleanly and unobtrusively.

## Brand Personality

Calm, clinical, trustworthy — three words: **precise, quiet, instrumented**. It should feel like a well-built internal dev tool or research instrument (closer to an IDE than a consumer app): no visual noise competing with the participant's own code, no persuasion, no flourish for its own sake. Voice/copy is plain and procedural (task instructions, gate prompts), never marketing-toned or playful.

## Anti-references

- **The superseded Streamlit prototype.** Not generic widget-in-a-box defaults, unstyled forms, or ad hoc layout — this is being explicitly replaced because it read as a prototype, not an instrument.
- **Gamified / playful UI.** No confetti, streaks, badges-as-rewards, encouraging microcopy, or delight-for-delight's-sake. This is a serious task, not an app to be charmed by.
- **Consumer SaaS marketing gloss.** No gradients, hero sections, or sales-toned copy anywhere in the study flow.
- **Any visual asymmetry between conditions.** Baseline and multi-agent/HITL screens must be built from the same component vocabulary, spacing, and polish level — a participant (or a reviewer of screenshots) should not be able to guess which condition is the "real" one from visual sophistication alone.

## Design Principles

1. **Neutrality across conditions is non-negotiable.** Component reuse, information density, and visual polish must be identical between the baseline and multi-agent flows — asymmetry here is a confound, not a design opinion.
2. **Unsupervised-remote means self-explanatory.** No researcher is present to clarify a confusing screen; every gate, hint, and instruction must be legible without external explanation.
3. **The interface is an instrument, not a product to be loved.** It recedes in favour of the participant's own code and reasoning; no gamification or persuasive design patterns that could inflate engagement artificially.
4. **Signal redundantly, never by hue alone.** Severity, status, and gate states (Bandit findings, hint levels, confidence, pass/fail) must be legible via shape/icon/text as well as color.
5. **The mentor model is one coherent system.** The hint ladder, annotation gate, and prediction gate should read as a considered, unified flow — not bolted-on modals interrupting a code editor.

## Accessibility & Inclusion

WCAG AA minimum. Severity/status indicators (currently color-only badges in `globals.css`: critical/high/medium/low in red/orange/yellow/green) must gain redundant non-color signaling — icon or text-weight distinction — so color-vision-deficient participants aren't disadvantaged in a way that could affect study data. Standard keyboard/focus accessibility applies throughout (Monaco editor, forms, gates).
