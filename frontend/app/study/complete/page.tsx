"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "motion/react";

const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];

const CONDITION_META: Record<string, { label: string; badge: string; accent: "neutral" | "ai" }> = {
  baseline: { label: "Baseline", badge: "Control", accent: "neutral" },
  multiagent: { label: "Multi-Agent", badge: "Experimental", accent: "ai" },
};

function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "—";
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function CompletePage() {
  return (
    <Suspense fallback={<div className="oled-scope min-h-screen" />}>
      <CompleteContent />
    </Suspense>
  );
}

function CompleteContent() {
  const searchParams = useSearchParams();

  const conditionKey = searchParams.get("condition");
  const condition = conditionKey ? CONDITION_META[conditionKey] : undefined;

  const durationParam = searchParams.get("duration");
  const durationSeconds = durationParam !== null ? Number(durationParam) : NaN;
  const durationLabel = formatDuration(durationSeconds);

  return (
    <div className="oled-scope relative flex min-h-screen items-center justify-center px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE_OUT }}
        className="w-full max-w-[420px] text-center"
      >
        <div className="check-pop mx-auto mb-6 flex h-[52px] w-[52px] items-center justify-center rounded-full border border-success bg-success-surface">
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        <h1 className="mb-2.5 text-xl font-medium tracking-[-0.4px] text-ink">Session Complete</h1>
        <p className="mb-8 text-[15px] leading-relaxed text-ink-muted">
          Thank you for participating. You may now close this browser tab.
        </p>

        <div className="cosmoq-card px-6 py-5 text-left">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Condition</p>
            {condition ? (
              <span
                className={`inline-block rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider ${
                  condition.accent === "ai"
                    ? "border-cosmoq-blue/35 bg-cosmoq-blue-tint text-cosmoq-blue-bright"
                    : "border-hairline-strong bg-oled-2 text-ink-faint"
                }`}
              >
                {condition.badge} · {condition.label}
              </span>
            ) : (
              <span className="text-sm text-ink-faint">—</span>
            )}
          </div>

          <div className="my-4 border-t border-hairline" />

          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Time on Task</p>
            <span className="font-mono text-sm text-ink">{durationLabel}</span>
          </div>
        </div>

        <p className="mt-8 text-xs text-ink-faint">
          All responses are anonymised and used for academic research purposes only.
        </p>
      </motion.div>
    </div>
  );
}
