"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, useReducedMotion, type Variants } from "motion/react";
import { fetchShuffledTasks, generateCode, type Task } from "@/lib/api";
import DebriefPage from "@/components/DebriefPage";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];
// Critically-damped spring — matches the no-overshoot settle-in feel extracted from
// cosmoq.framer.website's load-in animation (see frontend/docs/COSMOQ_INTERACTIONS.md).
const SPRING_SETTLE = { type: "spring", stiffness: 130, damping: 20, mass: 1 } as const;

/* ── Types ───────────────────────────────────────────────────────────────── */

type Phase = "loading" | "ready" | "generating" | "reviewing" | "complete";

interface TaskResult {
  code: string;
  duration: number;
  notes: string;
}

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function BaselinePage() {
  const router = useRouter();
  const prefersReducedMotion = useReducedMotion();
  const notesRef = useRef<HTMLTextAreaElement>(null);

  const [participantId, setParticipantId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskIndex, setTaskIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("loading");
  const [results, setResults] = useState<TaskResult[]>([]);
  const [notes, setNotes] = useState("");
  const [editedCode, setEditedCode] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);

  const currentResult = results[taskIndex] ?? null;
  const currentTask = tasks[taskIndex];

  const phaseVariants: Variants = prefersReducedMotion
    ? {
        initial: { opacity: 0 },
        animate: { opacity: 1, transition: { duration: 0.2 } },
        exit: { opacity: 0, transition: { duration: 0.1 } },
      }
    : {
        initial: { opacity: 0, y: 14, scale: 0.99 },
        animate: { opacity: 1, y: 0, scale: 1, transition: SPRING_SETTLE },
        exit: { opacity: 0, y: -8, scale: 0.99, transition: { duration: 0.14 } },
      };

  /* — init — */
  useEffect(() => {
    const pid = sessionStorage.getItem("participant_id");
    if (!pid) {
      router.replace("/");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setParticipantId(pid);

    const startIdx = parseInt(sessionStorage.getItem("task_start_index") ?? "0", 10);
    if (!isNaN(startIdx) && startIdx > 0) {
      setTaskIndex(startIdx);
      sessionStorage.removeItem("task_start_index");
    }

    fetchShuffledTasks()
      .then((t) => {
        setTasks(t);
        setPhase("ready");
      })
      .catch((err: Error) => {
        setApiError(
          `Could not reach the study server. Make sure the backend is running on port 8000.\n\n${err.message}`
        );
        setPhase("ready");
      });
  }, [router]);

  /* — generate — */
  async function handleGenerate() {
    if (!participantId || !tasks[taskIndex]) return;
    setPhase("generating");
    setApiError(null);
    try {
      const res = await generateCode({
        participant_id: participantId,
        task_id: tasks[taskIndex].task_id,
        task_order: taskIndex + 1,
      });
      setResults((prev) => {
        const next = [...prev];
        next[taskIndex] = { code: res.response, duration: res.duration_seconds, notes: "" };
        return next;
      });
      setEditedCode(res.response);
      setNotes("");
      setPhase("reviewing");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Generation failed. Check the backend.");
      setPhase("ready");
    }
  }

  /* — advance — */
  function handleNext() {
    setResults((prev) => {
      const next = [...prev];
      if (next[taskIndex]) next[taskIndex] = { ...next[taskIndex], code: editedCode, notes };
      return next;
    });
    if (taskIndex + 1 >= tasks.length) {
      setPhase("complete");
    } else {
      setTaskIndex((i) => i + 1);
      setNotes("");
      setEditedCode("");
      setPhase("ready");
    }
  }

  /* ── Completion ──────────────────────────────────────────────────────────── */

  if (phase === "complete") {
    return <DebriefPage participantId={participantId ?? ""} ambientClass="oled-ambient-orange" />;
  }

  /* ── Main layout ─────────────────────────────────────────────────────────── */

  return (
    <div className="oled-scope relative min-h-screen">
      <div className="oled-ambient-orange" />
      {/* Progress header */}
      <header className="sticky top-0 z-20 border-b border-hairline bg-oled-1">
        <div className="mx-auto flex max-w-[860px] items-center justify-between px-6 py-3.5">
          <div className="flex items-center gap-3.5">
            <ProgressDots total={tasks.length || 4} current={taskIndex} reviewing={phase === "reviewing"} />
            <span className="text-sm font-medium text-ink-secondary">
              {tasks.length > 0 ? `Task ${taskIndex + 1} of ${tasks.length}` : "Loading…"}
            </span>
          </div>
          {participantId && <span className="font-mono text-xs text-ink-faint">{participantId}</span>}
        </div>
      </header>

      {/* Content */}
      <main className="relative z-10 mx-auto max-w-[860px] px-6 py-8">
        {/* Error banner */}
        {apiError && phase !== "reviewing" && (
          <div
            role="alert"
            className="mb-6 flex items-start gap-3 rounded-2xl border border-danger-border/60 bg-danger-surface/70 px-5 py-4"
          >
            <span className="flex-shrink-0 font-bold text-danger-ink">✕</span>
            <p className="flex-1 whitespace-pre-wrap text-sm text-danger-ink">{apiError}</p>
            <button
              onClick={() => setApiError(null)}
              className="flex-shrink-0 cursor-pointer text-xs text-ink-muted transition-colors hover:text-ink-secondary"
            >
              dismiss
            </button>
          </div>
        )}

        {/* Task — shown across every phase, matching the multi-agent condition's structure */}
        {currentTask && (
          <div className="cosmoq-card-orange mb-6 p-6">
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
              Task {taskIndex + 1} of {tasks.length}
            </p>
            <p className="max-w-[72ch] text-base leading-relaxed tracking-[-0.48px] text-ink-secondary">
              {currentTask.text}
            </p>
          </div>
        )}

        <AnimatePresence mode="wait">
          <motion.div key={phase} variants={phaseVariants} initial="initial" animate="animate" exit="exit">
            {/* Loading skeleton */}
            {phase === "loading" && (
              <div className="cosmoq-card-orange p-6">
                <div className="skeleton mb-5 h-3 w-20 rounded-md" />
                <div className="skeleton mb-2.5 h-4 w-full rounded-md" />
                <div className="skeleton mb-2.5 h-4 w-[85%] rounded-md" />
                <div className="skeleton h-4 w-[70%] rounded-md" />
              </div>
            )}

            {/* Ready — generate button */}
            {phase === "ready" && !apiError && tasks.length > 0 && (
              <div className="flex justify-center py-2">
                <div className="w-[260px]">
                  <Btn onClick={handleGenerate}>Generate Code</Btn>
                </div>
              </div>
            )}

            {/* Generating — skeleton editor */}
            {phase === "generating" && (
              <div className="cosmoq-card-orange overflow-hidden">
                <div className="flex items-center justify-between border-b border-hairline px-5 py-3">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                    Generating Code…
                  </span>
                  <Spinner className="text-cosmoq-orange-bright" />
                </div>
                <EditorSkeleton />
              </div>
            )}

            {/* Reviewing — code + notes + next */}
            {phase === "reviewing" && currentResult && (
              <>
                <div className="cosmoq-card-orange mb-6 overflow-hidden">
                  <div className="flex items-center justify-between border-b border-hairline px-5 py-3">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                      Generated Code (edit if needed)
                    </span>
                    <span className="font-mono text-xs text-ink-faint">
                      {currentResult.duration.toFixed(1)}s
                    </span>
                  </div>
                  <MonacoEditor
                    height="440px"
                    language="python"
                    value={editedCode}
                    theme="vs-dark"
                    onChange={(val) => setEditedCode(val ?? "")}
                    options={{
                      minimap: { enabled: false },
                      lineNumbers: "on",
                      wordWrap: "on",
                      scrollBeyondLastLine: false,
                      fontSize: 13,
                      padding: { top: 16, bottom: 16 },
                    }}
                  />
                </div>

                <div className="cosmoq-card-orange mb-6 p-6">
                  <label
                    htmlFor="baseline-notes"
                    className="mb-2.5 block text-[11px] font-semibold uppercase tracking-wider text-ink-faint"
                  >
                    Notes <span className="font-normal normal-case text-ink-faint">(optional)</span>
                  </label>
                  <Field
                    id="baseline-notes"
                    inputRef={notesRef}
                    value={notes}
                    onChange={setNotes}
                    placeholder="Record any observations, concerns, or thoughts about this code."
                    rows={4}
                  />
                </div>

                <div className="flex justify-end">
                  <div className="w-[220px]">
                    <Btn onClick={handleNext}>
                      {taskIndex + 1 >= tasks.length ? "Complete Study" : "Next Task →"}
                    </Btn>
                  </div>
                </div>
              </>
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────────── */

function ProgressDots({
  total,
  current,
  reviewing,
}: {
  total: number;
  current: number;
  reviewing: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: total }).map((_, i) => {
        const done = i < current || (i === current && reviewing);
        const active = i === current && !reviewing;
        return (
          <div
            key={i}
            className={`h-1.5 rounded-full transition-all duration-300 ${active ? "w-8" : "w-2"} ${
              done ? "bg-success" : active ? "bg-cosmoq-orange" : "bg-hairline-strong"
            }`}
          />
        );
      })}
    </div>
  );
}

function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 animate-spin ${className}`} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function Btn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="cosmoq-pill-orange min-h-[44px] w-full cursor-pointer rounded-full border border-transparent bg-oled-2 px-6 text-sm font-medium text-white transition-all duration-150 hover:bg-oled-3 active:scale-[0.97] disabled:cursor-not-allowed disabled:border-hairline disabled:bg-transparent disabled:text-ink-faint disabled:opacity-60 disabled:active:scale-100 disabled:shadow-none"
    >
      {children}
    </button>
  );
}

function Field({
  id,
  inputRef,
  value,
  onChange,
  placeholder,
  rows,
}: {
  id?: string;
  inputRef?: React.Ref<HTMLTextAreaElement>;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows: number;
}) {
  return (
    <textarea
      id={id}
      ref={inputRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full resize-none rounded-2xl border border-hairline-strong bg-oled-2 px-4 py-3 text-sm leading-relaxed text-ink outline-none transition-colors duration-150 placeholder:text-ink-faint focus:border-cosmoq-orange focus:ring-1 focus:ring-cosmoq-orange/40"
    />
  );
}

function EditorSkeleton() {
  return (
    <div className="min-h-[440px] bg-[#0a0a0a] px-6 py-5">
      {[78, 62, 91, 54, 70, 45, 83, 58, 74, 49, 66, 38].map((w, i) => (
        <div
          key={i}
          className="skeleton mb-2.5"
          style={{ height: "14px", width: `${w}%`, borderRadius: "6px", animationDelay: `${i * 55}ms` }}
        />
      ))}
    </div>
  );
}
