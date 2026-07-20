"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { AnimatePresence, motion, type Variants } from "motion/react";
import {
  fetchShuffledTasks,
  startSession,
  resumeSession,
  fetchStepCaps,
  requestStepHint,
  requestNextHint,
  requestSecurityHint,
  finalizeCode,
  reviseCode,
  type Task,
  type AgentStateData,
  type ThreatEntry,
  type ReviewFinding,
  type HintRecord,
  type HintLevel,
  type StepHintCap,
} from "@/lib/api";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];
const EASE_IN: [number, number, number, number] = [0.4, 0, 1, 1];
// Critically-damped spring — matches the no-overshoot settle-in feel extracted from
// cosmoq.framer.website's load-in animation (see frontend/docs/COSMOQ_INTERACTIONS.md).
const SPRING_SETTLE = { type: "spring", stiffness: 130, damping: 20, mass: 1 } as const;

/* ── Types ───────────────────────────────────────────────────────────────── */

type UIStage =
  | "loading"
  | "starting"
  | "processing"
  | "plan_review"
  | "threat_review"
  | "coding"
  | "finalizing"
  | "code_review"
  | "task_complete"
  | "agent_error"
  | "all_complete";

function detectStage(state: AgentStateData): UIStage {
  if (state.current_stage === "error") return "agent_error";
  if (state.plan && !state.plan_decision) return "plan_review";
  if (state.threats && !state.threats_decision) return "threat_review";
  if (state.current_stage === "coding_in_progress") return "coding";
  if (state.review_findings != null && !state.review_decision) return "code_review";
  if (state.current_stage === "complete") return "task_complete";
  return "loading";
}

const STAGE_LABELS = ["Plan", "Threats", "Code", "Review", "Verify"] as const;
const STAGE_ORDER: UIStage[] = ["plan_review", "threat_review", "coding", "code_review", "task_complete"];

function stageIndex(s: UIStage) {
  return STAGE_ORDER.indexOf(s);
}

function now() {
  return new Date().toISOString();
}

/* ── Motion variants — micro-interactions for HITL stage transitions ───────
   Exit is deliberately faster than enter: it keeps the pipeline feeling
   responsive while giving each new stage room to settle in. ── */

const stageVariants: Variants = {
  initial: { opacity: 0, y: 14, scale: 0.99 },
  animate: { opacity: 1, y: 0, scale: 1, transition: SPRING_SETTLE },
  exit: { opacity: 0, y: -8, scale: 0.99, transition: { duration: 0.16, ease: EASE_IN } },
};

const revealVariants: Variants = {
  initial: { opacity: 0, y: 8, scale: 0.97 },
  animate: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.26, ease: EASE_OUT } },
  exit: { opacity: 0, y: -4, scale: 0.98, transition: { duration: 0.14, ease: EASE_IN } },
};

const staggerContainer: Variants = {
  animate: { transition: { staggerChildren: 0.06 } },
};

const staggerItem: Variants = {
  initial: { opacity: 0, y: 14, scale: 0.98 },
  animate: { opacity: 1, y: 0, scale: 1, transition: SPRING_SETTLE },
};

/* ── Page ────────────────────────────────────────────────────────────────── */

export default function MultiAgentPage() {
  const router = useRouter();
  const [participantId, setParticipantId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskIndex, setTaskIndex] = useState(0);
  const [uiStage, setUiStage] = useState<UIStage>("loading");
  const [agentState, setAgentState] = useState<AgentStateData>({});
  const [threadId, setThreadId] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [processingLabel, setProcessingLabel] = useState("Working…");
  const [processingPill, setProcessingPill] = useState<number | null>(null);

  // Coding stage
  const [code, setCode] = useState("");
  const codingStart = useRef<Date | null>(null);

  // Plan revision history (shown as conversation thread across multiple rounds)
  const [planHistory, setPlanHistory] = useState<Array<{ plan: NonNullable<AgentStateData["plan"]>; feedback: string }>>([]);

  // Annotation gate
  const [showGate, setShowGate] = useState(false);
  const [whatCodeDoes, setWhatCodeDoes] = useState("");
  const [threatsAddressed, setThreatsAddressed] = useState<string[]>([]);
  const [confidence, setConfidence] = useState(0);
  const [predictions, setPredictions] = useState<string[]>([]);

  /* — helpers — */
  function applyState(s: AgentStateData) {
    setAgentState(s);
    setProcessingPill(null);
    const stage = detectStage(s);
    setUiStage(stage);
    if (stage === "coding") codingStart.current = codingStart.current ?? new Date();
  }

  async function callResume(update: Record<string, unknown>, label: string) {
    if (!threadId) return;
    setApiError(null);
    setProcessingLabel(label);
    setUiStage("processing");
    try {
      const res = await resumeSession(threadId, update);
      applyState(res.state);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Resume failed");
      setUiStage(detectStage(agentState));
    }
  }

  /* — init — */
  useEffect(() => {
    const pid = localStorage.getItem("participant_id");
    if (!pid) { router.replace("/"); return; }
    setParticipantId(pid);
    fetchShuffledTasks()
      .then((t) => { setTasks(t); setUiStage("starting"); })
      .catch((e) => setApiError(`Could not load tasks: ${e.message}`));
  }, [router]);

  /* — start session when we have tasks and pid — */
  useEffect(() => {
    if (uiStage !== "starting" || !participantId || tasks.length === 0) return;
    (async () => {
      setProcessingLabel("Planner is working…");
      setUiStage("processing");
      try {
        const res = await startSession({
          participant_id: participantId,
          task_id: tasks[taskIndex].task_id,
          task_order: taskIndex + 1,
        });
        setThreadId(res.thread_id);
        applyState(res.state);
      } catch (e) {
        setApiError(e instanceof Error ? e.message : "Session start failed");
        setUiStage("loading");
      }
    })();
  }, [uiStage, participantId, tasks, taskIndex]);

  /* — plan decision — */
  async function handlePlanDecision(action: "approve" | "revise", revision?: string) {
    if (action === "revise" && agentState.plan) {
      setPlanHistory((prev) => [...prev, { plan: agentState.plan!, feedback: revision ?? "" }]);
    }
    setProcessingPill(action === "approve" ? 1 : 0);
    await callResume(
      { plan_decision: { action, revised_content: revision ?? null, timestamp: now() } },
      action === "approve"
        ? "Threat Modeller is querying NIST NVD. This can take 20 to 40 seconds…"
        : "Planner is revising the plan…"
    );
  }

  /* — threat decision — */
  async function handleThreatDecision(action: "approve" | "revise", revision?: string) {
    setProcessingPill(action === "approve" ? 2 : 1);
    await callResume(
      { threats_decision: { action, revised_content: revision ?? null, timestamp: now() } },
      action === "approve" ? "Setting up coding environment…" : "Threat Modeller is revising…"
    );
  }

  /* — finalize — hints log is passed in from CodingStage — */
  async function handleFinalize(hintsLog: HintRecord[]) {
    if (!threadId || !whatCodeDoes || confidence === 0) return;
    setApiError(null);
    setProcessingPill(3);
    setUiStage("finalizing");
    const elapsed = codingStart.current
      ? (Date.now() - codingStart.current.getTime()) / 1000
      : 0;
    try {
      const res = await finalizeCode(threadId, {
        user_code: code,
        annotations: {
          what_does_code_do: whatCodeDoes,
          threats_addressed: threatsAddressed,
          submitted_at: now(),
        },
        confidence_rating: confidence,
        hints_requested: hintsLog,
        time_in_coding_seconds: Math.round(elapsed),
        pre_review_prediction: predictions.length > 0 ? predictions : undefined,
      });
      applyState(res.state);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Submission failed");
      setUiStage("coding");
    }
  }

  /* — review decision — */
  async function handleReviewAcknowledge() {
    setProcessingPill(4);
    await callResume(
      { review_decision: { action: "approve", revised_content: null, timestamp: now() } },
      "Verifier is running final checks…"
    );
  }

  /* — revise code after review — */
  async function handleRevise(newCode: string) {
    setCode(newCode);
    setApiError(null);
    setProcessingPill(3);
    setProcessingLabel("Re-running Code Reviewer on revised code…");
    setUiStage("processing");
    try {
      const res = await reviseCode(threadId!, newCode);
      applyState(res.state);
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "Revision failed");
      setUiStage("code_review");
    }
  }

  /* — next task — */
  function handleNextTask() {
    const next = taskIndex + 1;
    if (next >= tasks.length) {
      setUiStage("all_complete");
      return;
    }
    setTaskIndex(next);
    setThreadId(null);
    setAgentState({});
    setCode("");
    setPlanHistory([]);
    setShowGate(false);
    setWhatCodeDoes("");
    setThreatsAddressed([]);
    setConfidence(0);
    setPredictions([]);
    codingStart.current = null;
    setProcessingPill(null);
    setUiStage("starting");
  }

  /* ── Render ──────────────────────────────────────────────────────────────── */

  if (uiStage === "all_complete") {
    return (
      <div className="oled-scope relative flex min-h-screen items-center justify-center px-6 py-12">
        <div className="oled-ambient" />
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE_OUT }}
          className="relative z-10 max-w-[420px] text-center"
        >
          <div className="check-pop mx-auto mb-6 flex h-[52px] w-[52px] items-center justify-center rounded-full border border-success bg-success-surface">
            <svg width="22" height="22" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="mb-2.5 text-xl font-medium tracking-[-0.4px] text-ink">All {tasks.length} tasks complete</h1>
          <p className="text-[15px] text-ink-muted">Thank you for participating. You may now close this browser tab.</p>
        </motion.div>
      </div>
    );
  }

  const currentTask = tasks[taskIndex];
  const threats = (agentState.threats ?? []) as ThreatEntry[];
  const findings = (agentState.review_findings ?? []) as ReviewFinding[];

  const pillActive =
    uiStage === "task_complete"
      ? STAGE_LABELS.length
      : uiStage === "processing" || uiStage === "finalizing"
      ? processingPill ?? 0
      : stageIndex(uiStage);

  return (
    <div className="oled-scope relative min-h-screen">
      <div className="oled-ambient" />

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="elevate-glass sticky top-0 z-20 border-b border-hairline">
        <div className="mx-auto max-w-[1080px] px-6 py-3">
          {/* Row 1: task progress + pid */}
          <div className="mb-2.5 flex items-center justify-between">
            <div className="flex items-center gap-3.5">
              <ProgressDots total={tasks.length || 4} current={taskIndex} done={uiStage === "task_complete"} />
              <span className="text-sm font-medium text-ink-secondary">
                {tasks.length > 0 ? `Task ${taskIndex + 1} of ${tasks.length}` : "Loading…"}
              </span>
            </div>
            {participantId && <span className="font-mono text-xs text-ink-faint">{participantId}</span>}
          </div>

          {/* Row 2: stage pills */}
          <div className="flex items-center gap-1">
            {STAGE_LABELS.map((label, i) => {
              const isDone = uiStage === "task_complete" ? true : pillActive > i;
              const isActive = uiStage === "task_complete" ? false : pillActive === i;
              return (
                <div key={label} className="flex items-center gap-1">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors duration-300 ${
                      isDone
                        ? "border-success-deep/60 bg-success-surface text-success-ink"
                        : isActive
                        ? "stage-pulse border-ai-border bg-ai-surface text-ai-bright"
                        : "border-hairline bg-transparent text-ink-faint"
                    }`}
                  >
                    {isDone && (
                      <span key={`done-${label}`} className="check-pop inline-block">
                        ✓
                      </span>
                    )}
                    {label}
                  </span>
                  {i < STAGE_LABELS.length - 1 && <span className="text-xs text-ink-faint">›</span>}
                </div>
              );
            })}
          </div>
        </div>
      </header>

      {/* ── Content ────────────────────────────────────────────────────────── */}
      <main className="relative z-10 mx-auto max-w-[1080px] px-6 pb-20 pt-8">

        {/* Error banner */}
        {apiError && (
          <div className="mb-5 flex items-start gap-3 rounded-xl border border-danger-border/60 bg-danger-surface/70 px-5 py-4">
            <span className="flex-shrink-0 font-bold text-danger-ink">✕</span>
            <p className="flex-1 text-sm text-danger-ink">{apiError}</p>
            <button onClick={() => setApiError(null)} className="cursor-pointer text-xs text-ink-muted hover:text-ink-secondary">
              dismiss
            </button>
          </div>
        )}

        {/* Task description (shown in all stages) */}
        {currentTask && (
          <div className="elevate-1 accent-wash-green mb-5 rounded-xl p-6">
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Task</p>
            <p className="max-w-[72ch] text-base leading-relaxed tracking-[-0.48px] text-ink-secondary">{currentTask.text}</p>
          </div>
        )}

        {/* Stage content — every HITL transition gets a settle-in / quick-exit micro-interaction */}
        <AnimatePresence mode="wait">
          <motion.div key={uiStage} variants={stageVariants} initial="initial" animate="animate" exit="exit">
            {(uiStage === "loading" || uiStage === "starting" || uiStage === "processing" || uiStage === "finalizing") && (
              <ProcessingCard
                label={
                  uiStage === "finalizing"
                    ? "Code Reviewer is running…"
                    : uiStage === "starting" || uiStage === "processing"
                    ? processingLabel
                    : "Loading…"
                }
              />
            )}

            {uiStage === "plan_review" && agentState.plan && (
              <PlanReview plan={agentState.plan} history={planHistory} onDecide={handlePlanDecision} />
            )}

            {uiStage === "threat_review" && threats.length > 0 && (
              <ThreatReview threats={threats} plan={agentState.plan ?? null} onDecide={handleThreatDecision} />
            )}

            {uiStage === "coding" && threadId && (
              <CodingStage
                threadId={threadId}
                code={code}
                onCodeChange={setCode}
                plan={agentState.plan ?? null}
                threats={threats}
                showGate={showGate}
                onShowGate={() => setShowGate(true)}
                whatCodeDoes={whatCodeDoes}
                onWhatCodeDoes={setWhatCodeDoes}
                threatsAddressed={threatsAddressed}
                onThreatsAddressed={setThreatsAddressed}
                confidence={confidence}
                onConfidence={setConfidence}
                predictions={predictions}
                onPredictions={setPredictions}
                onFinalize={handleFinalize}
              />
            )}

            {uiStage === "code_review" && (
              <CodeReview
                findings={findings}
                predictionAccuracy={agentState.prediction_accuracy ?? null}
                plan={agentState.plan ?? null}
                threats={threats}
                code={code}
                onAcknowledge={handleReviewAcknowledge}
                onRevise={handleRevise}
              />
            )}

            {uiStage === "agent_error" && (
              <AgentError
                message={agentState.error ?? "An agent failed to complete."}
                onRetry={() => {
                  setAgentState({});
                  setThreadId(null);
                  setUiStage("starting");
                }}
              />
            )}

            {uiStage === "task_complete" && (
              <TaskComplete taskIndex={taskIndex} totalTasks={tasks.length} onNext={handleNextTask} />
            )}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

/* ── Icons — SVG only, no emoji-as-icon ──────────────────────────────────── */

function SparkleIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" className={className} aria-hidden="true">
      <path d="M8 1.2c.2 0 .38.14.43.34l.9 3.5a2.6 2.6 0 0 0 1.87 1.87l3.5.9a.45.45 0 0 1 0 .86l-3.5.9a2.6 2.6 0 0 0-1.87 1.87l-.9 3.5a.45.45 0 0 1-.86 0l-.9-3.5a2.6 2.6 0 0 0-1.87-1.87l-3.5-.9a.45.45 0 0 1 0-.86l3.5-.9A2.6 2.6 0 0 0 6.54 5.04l.9-3.5c.05-.2.23-.34.43-.34z" />
    </svg>
  );
}

function ShieldIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <path d="M8 1.5l5.2 1.9v3.7c0 3.4-2.2 6.2-5.2 7.4-3-1.2-5.2-4-5.2-7.4V3.4L8 1.5z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
    </svg>
  );
}

/* ── Local Tailwind primitives (scoped to this page) ────────────────────── */

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
  type = "button",
  variant = "primary",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  variant?: "primary" | "success" | "ghost" | "ai";
}) {
  const variants: Record<string, string> = {
    primary: "border border-transparent bg-signal-deep text-white hover:bg-signal hover:shadow-[0_0_18px_2px_rgba(34,197,94,0.4)]",
    success: "border border-transparent bg-success-deep text-white hover:bg-success hover:shadow-[0_0_18px_2px_rgba(22,163,74,0.4)]",
    ghost: "border border-hairline-strong bg-oled-2 text-ink-secondary hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]",
    ai: "border border-ai-border bg-ai-surface text-ai-bright hover:bg-ai/14 hover:shadow-[0_0_18px_2px_rgba(34,197,94,0.4)]",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-oled-1 disabled:text-ink-faint disabled:opacity-60 disabled:active:scale-100 ${variants[variant]}`}
    >
      {children}
    </button>
  );
}

function Field({
  value,
  onChange,
  placeholder,
  rows,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  autoFocus?: boolean;
}) {
  const base =
    "w-full rounded-lg border border-hairline-strong bg-oled-2 px-3.5 py-2.5 text-sm text-ink outline-none transition-all duration-150 placeholder:text-ink-faint focus:border-signal focus:ring-1 focus:ring-signal/40";
  if (rows) {
    return (
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className={`${base} resize-none leading-relaxed`}
      />
    );
  }
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoFocus={autoFocus}
      autoComplete="off"
      spellCheck={false}
      className={base}
    />
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity?.toLowerCase();
  const map: Record<string, string> = {
    critical: "border-red-800/60 bg-red-950/60 text-red-300",
    high: "border-orange-800/50 bg-orange-950/50 text-orange-300",
    medium: "border-yellow-800/40 bg-yellow-950/40 text-yellow-300",
  };
  const cls = map[s] ?? "border-green-800/40 bg-green-950/40 text-green-300";
  const label = s === "critical" ? "Critical" : s === "high" ? "High" : s === "medium" ? "Medium" : "Low";
  return <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${cls}`}>{label}</span>;
}

function severityElevateClass(severity: string) {
  const s = severity?.toLowerCase();
  if (s === "critical") return "elevate-critical";
  if (s === "high") return "elevate-high";
  if (s === "medium") return "elevate-medium";
  return "elevate-low";
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="elevate-1 accent-wash-green rounded-xl p-5">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{title}</p>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="mb-1 text-sm font-semibold text-ink-secondary">{children}</p>;
}

function CollapsibleRef({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="elevate-1 accent-wash-green overflow-hidden rounded-xl">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left transition-colors hover:bg-white/5"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">{title}</span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
          className="text-[10px] text-ink-faint"
        >
          ▼
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE_OUT }}
            className="border-t border-hairline"
          >
            <div className="px-4 pb-4 pt-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div className="min-h-[380px] bg-oled-1 px-6 py-5">
      {[78, 62, 91, 54, 70, 45, 83, 58, 74, 49].map((w, i) => (
        <div
          key={i}
          className="skeleton mb-2.5"
          style={{ height: "14px", width: `${w}%`, borderRadius: "6px", animationDelay: `${i * 55}ms` }}
        />
      ))}
    </div>
  );
}

/* ── Shared status panels ─────────────────────────────────────────────────── */

function ProgressDots({ total, current, done }: { total: number; current: number; done: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: total }).map((_, i) => {
        const isDone = i < current || (i === current && done);
        const isActive = i === current && !done;
        return (
          <div
            key={i}
            className={`h-1.5 rounded-full transition-all duration-300 ${isActive ? "w-8" : "w-2"} ${
              isDone ? "bg-success" : isActive ? "bg-signal" : "bg-hairline-strong"
            }`}
          />
        );
      })}
    </div>
  );
}

function ProcessingCard({ label }: { label: string }) {
  const isSlowOp = label.includes("NIST") || label.includes("Threat");
  return (
    <div className="elevate-2 accent-wash-green rounded-2xl p-6 text-center">
      <div className={`flex items-center justify-center gap-3 ${isSlowOp ? "mb-2.5" : ""}`}>
        <Spinner className="text-ai-bright" />
        <span className="text-sm text-ink-secondary">{label}</span>
      </div>
      {isSlowOp && (
        <p className="text-xs text-ink-faint">
          The Threat Modeller queries the NIST NVD vulnerability database in real time. This typically takes 20 to 40 seconds.
        </p>
      )}
    </div>
  );
}

/* ── Plan Review ─────────────────────────────────────────────────────────── */

function PlanReview({ plan, history, onDecide }: {
  plan: NonNullable<AgentStateData["plan"]>;
  history: Array<{ plan: NonNullable<AgentStateData["plan"]>; feedback: string }>;
  onDecide: (action: "approve" | "revise", revision?: string) => void;
}) {
  const [revision, setRevision] = useState("");
  const [showRevise, setShowRevise] = useState(false);
  const isRevision = history.length > 0;

  return (
    <div className="flex flex-col gap-4">
      <SectionLabel>Planner{isRevision ? ` (revision ${history.length + 1})` : ""}</SectionLabel>

      {/* Previous rounds */}
      {history.map((round, i) => (
        <div key={i} className="opacity-55">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Round {i + 1} (superseded)</p>
          <div className="elevate-1 mb-2 rounded-xl p-5">
            <p className="mb-2 text-xs font-medium text-ink-faint">Scope</p>
            <p className="text-[13px] leading-relaxed text-ink-muted">{round.plan.scope}</p>
          </div>
          <div className="elevate-1 flex items-start gap-2.5 rounded-lg p-4">
            <span className="flex-shrink-0 pt-px text-[11px] font-semibold text-ink-faint">Your feedback</span>
            <p className="text-[13px] italic leading-relaxed text-ink-muted">&quot;{round.feedback}&quot;</p>
          </div>
        </div>
      ))}

      {/* Current plan */}
      <InfoCard title="Scope">
        <p className="text-sm leading-relaxed text-ink-secondary">{plan.scope}</p>
      </InfoCard>

      <InfoCard title="Implementation Steps">
        <ol className="m-0 list-decimal space-y-1.5 pl-5">
          {plan.steps.map((s, i) => (
            <li key={i} className="text-sm leading-relaxed text-ink-secondary">{s}</li>
          ))}
        </ol>
      </InfoCard>

      <InfoCard title="Security Requirements">
        <ul className="m-0 list-disc space-y-1.5 pl-5">
          {plan.security_requirements.map((r, i) => (
            <li key={i} className="text-sm leading-relaxed text-ink-secondary">{r}</li>
          ))}
        </ul>
      </InfoCard>

      {/* Actions */}
      <AnimatePresence mode="wait" initial={false}>
        {!showRevise ? (
          <motion.div key="actions" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="flex justify-end gap-3">
            <button onClick={() => setShowRevise(true)} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
              Request Revision
            </button>
            <div className="w-[180px]">
              <Btn onClick={() => onDecide("approve")}>Approve Plan</Btn>
            </div>
          </motion.div>
        ) : (
          <motion.div key="revise" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="elevate-2 accent-wash-green rounded-xl p-5">
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">What would you like changed?</p>
            <Field value={revision} onChange={setRevision} placeholder="e.g. Add input validation to the steps. Remove the caching requirement. It's out of scope." rows={3} />
            <div className="mt-3 flex justify-end gap-2.5">
              <button onClick={() => { setShowRevise(false); setRevision(""); }} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
                Cancel
              </button>
              <div className="w-[180px]">
                <Btn onClick={() => { onDecide("revise", revision); setShowRevise(false); setRevision(""); }} disabled={!revision.trim()}>
                  Submit Feedback
                </Btn>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Threat Review ───────────────────────────────────────────────────────── */

function ThreatReview({ threats, plan, onDecide }: {
  threats: ThreatEntry[];
  plan: NonNullable<AgentStateData["plan"]> | null;
  onDecide: (action: "approve" | "revise", revision?: string) => void;
}) {
  const [revision, setRevision] = useState("");
  const [showRevise, setShowRevise] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      {plan && (
        <CollapsibleRef title="Plan (approved)" defaultOpen={false}>
          <ol className="m-0 list-decimal space-y-1 pl-[18px]">
            {plan.steps.map((s, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-ink-muted">{s}</li>
            ))}
          </ol>
        </CollapsibleRef>
      )}

      <SectionLabel>Threat Model: {threats.length} threat{threats.length !== 1 ? "s" : ""} identified</SectionLabel>

      <motion.div variants={staggerContainer} initial="initial" animate="animate" className="flex flex-col gap-4">
        {threats.map((t) => (
          <motion.div key={t.cwe_id} variants={staggerItem} className="elevate-1 accent-wash-green rounded-xl p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-[13px] font-semibold text-signal-bright">{t.cwe_id}</span>
              <span className="text-sm font-semibold text-ink">{t.name}</span>
              <SeverityBadge severity={t.severity} />
            </div>
            <p className="mb-2.5 text-[13px] leading-relaxed text-ink-muted">{t.description}</p>
            <div className="rounded-lg bg-oled-3 p-3.5">
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Mitigation</p>
              <p className="text-[13px] leading-relaxed text-ink-secondary">{t.mitigation}</p>
            </div>
          </motion.div>
        ))}
      </motion.div>

      <AnimatePresence mode="wait" initial={false}>
        {!showRevise ? (
          <motion.div key="actions" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="flex justify-end gap-3">
            <button onClick={() => setShowRevise(true)} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
              Request Revision
            </button>
            <div className="w-[200px]">
              <Btn onClick={() => onDecide("approve")}>Approve Threat Model</Btn>
            </div>
          </motion.div>
        ) : (
          <motion.div key="revise" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="elevate-2 accent-wash-green rounded-xl p-5">
            <p className="mb-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Revision Request</p>
            <Field value={revision} onChange={setRevision} placeholder="Describe what you'd like changed…" rows={3} />
            <div className="mt-3 flex justify-end gap-2.5">
              <button onClick={() => setShowRevise(false)} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
                Cancel
              </button>
              <div className="w-[180px]">
                <Btn onClick={() => onDecide("revise", revision)} disabled={!revision.trim()}>Submit Revision</Btn>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Coding Stage ────────────────────────────────────────────────────────── */

const LEVEL_ORDER: HintLevel[] = ["direction", "pseudocode", "partial", "full"];
const LEVEL_LABELS: Record<HintLevel, string> = {
  direction: "Direction", pseudocode: "Pseudocode", partial: "Partial Code", full: "Full Code",
};
const LEVEL_DEPTH: Record<string, number> = { direction: 1, pseudocode: 2, partial: 3, full: 4 };

function CodingStage({
  threadId, code, onCodeChange, plan, threats,
  showGate, onShowGate,
  whatCodeDoes, onWhatCodeDoes,
  threatsAddressed, onThreatsAddressed,
  confidence, onConfidence,
  predictions, onPredictions,
  onFinalize,
}: {
  threadId: string;
  code: string; onCodeChange: (v: string) => void;
  plan: NonNullable<AgentStateData["plan"]> | null;
  threats: ThreatEntry[];
  showGate: boolean; onShowGate: () => void;
  whatCodeDoes: string; onWhatCodeDoes: (v: string) => void;
  threatsAddressed: string[]; onThreatsAddressed: (v: string[]) => void;
  confidence: number; onConfidence: (v: number) => void;
  predictions: string[]; onPredictions: (v: string[]) => void;
  onFinalize: (hintsLog: HintRecord[]) => void;
}) {
  // Step caps (fetched once on mount)
  const [stepCaps, setStepCaps] = useState<StepHintCap[]>([]);
  const [capsLoading, setCapsLoading] = useState(true);

  // Per-step unlock depth (step_index → highest LEVEL_DEPTH reached)
  const [stepUnlocked, setStepUnlocked] = useState<Record<number, number>>({});

  // Active step hint
  const [activeStepHint, setActiveStepHint] = useState<{
    step: number; level: string; text: string; securityNote: string;
  } | null>(null);
  const [stepHintLoading, setStepHintLoading] = useState<{ step: number; level: string } | null>(null);

  // Adaptive "what should I do next?" hint
  const [nextHint, setNextHint] = useState<{ text: string; securityNote: string } | null>(null);
  const [nextHintLoading, setNextHintLoading] = useState(false);

  // Security hint (whole-code pass)
  const [securityHint, setSecurityHint] = useState<string | null>(null);
  const [securityHintLoading, setSecurityHintLoading] = useState(false);

  // Hint log — passed to onFinalize
  const [hintsLog, setHintsLog] = useState<HintRecord[]>([]);

  useEffect(() => {
    fetchStepCaps(threadId)
      .then((r) => setStepCaps(r.step_caps))
      .catch(() => { /* caps unavailable — all levels default to unlocked */ })
      .finally(() => setCapsLoading(false));
  }, [threadId]);

  function capDepthFor(stepIndex: number): number {
    const cap = stepCaps.find((c) => c.step_index === stepIndex);
    return cap ? (LEVEL_DEPTH[cap.max_level] ?? 4) : 2; // default pseudocode if no caps
  }

  function isAvailable(stepIndex: number, level: HintLevel): boolean {
    const depth = LEVEL_DEPTH[level];
    return depth <= capDepthFor(stepIndex) && depth <= (stepUnlocked[stepIndex] ?? 0) + 1;
  }

  function isUsed(stepIndex: number, level: HintLevel): boolean {
    return (stepUnlocked[stepIndex] ?? 0) >= LEVEL_DEPTH[level];
  }

  async function handleStepHint(stepIndex: number, level: HintLevel) {
    if (stepHintLoading) return;
    setStepHintLoading({ step: stepIndex, level });
    setNextHint(null);
    try {
      const res = await requestStepHint(threadId, stepIndex, level);
      setActiveStepHint({ step: stepIndex, level, text: res.content, securityNote: res.security_note });
      setStepUnlocked((prev) => ({ ...prev, [stepIndex]: Math.max(prev[stepIndex] ?? 0, LEVEL_DEPTH[level]) }));
      const record: HintRecord = { step_index: stepIndex, level, timestamp: new Date().toISOString() };
      setHintsLog((prev) => [...prev, record]);
    } catch { /* silently ignore */ }
    finally { setStepHintLoading(null); }
  }

  async function handleNextHint() {
    if (nextHintLoading || code.length < 20) return;
    setNextHintLoading(true);
    setActiveStepHint(null);
    try {
      const res = await requestNextHint(threadId, code);
      setNextHint({ text: res.content, securityNote: res.security_note });
      const record: HintRecord = { step_index: -1, level: "adaptive", timestamp: new Date().toISOString() };
      setHintsLog((prev) => [...prev, record]);
    } catch { /* silently ignore */ }
    finally { setNextHintLoading(false); }
  }

  async function handleSecurityHint() {
    if (securityHintLoading || code.length < 30) return;
    setSecurityHintLoading(true);
    try {
      const res = await requestSecurityHint(threadId, code);
      setSecurityHint(res.hint);
      const record: HintRecord = { step_index: -1, level: "security", timestamp: new Date().toISOString() };
      setHintsLog((prev) => [...prev, record]);
    } catch { /* silently ignore */ }
    finally { setSecurityHintLoading(false); }
  }

  function toggleThreat(cweId: string) {
    onThreatsAddressed(
      threatsAddressed.includes(cweId)
        ? threatsAddressed.filter((x) => x !== cweId)
        : [...threatsAddressed, cweId]
    );
  }

  function togglePrediction(cweId: string) {
    onPredictions(
      predictions.includes(cweId)
        ? predictions.filter((x) => x !== cweId)
        : [...predictions, cweId]
    );
  }

  const canSubmit = whatCodeDoes.trim().length > 0 && confidence > 0 && code.trim().length > 0;
  const hasSidebar = plan || threats.length > 0;
  const steps = plan?.steps ?? [];

  return (
    <div className="flex items-start gap-5">

      {/* ── Main column ──────────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <SectionLabel>Write your code. Use the hints if you need help.</SectionLabel>

        {/* Editor */}
        <div className="elevate-2 accent-wash-green overflow-hidden rounded-xl">
          <MonacoEditor
            height="380px"
            language="python"
            value={code}
            theme="vs-dark"
            onChange={(val) => onCodeChange(val ?? "")}
            options={{ minimap: { enabled: false }, lineNumbers: "on", wordWrap: "on", scrollBeyondLastLine: false, fontSize: 13, padding: { top: 16, bottom: 16 } }}
          />
        </div>

        {/* ── Hints — layered floating panels, one per concern ── */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-1.5">
            <SparkleIcon className="h-3.5 w-3.5 text-ai-bright" />
            <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Hints</p>
          </div>

          {/* Adaptive: "What should I do next?" — floating AI query card */}
          <div className="elevate-glass accent-wash-green rounded-xl p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="flex items-center gap-1.5 text-[13px] font-medium text-ai-bright">
                <SparkleIcon className="h-3.5 w-3.5" />
                What should I do next?
              </p>
              <button
                onClick={handleNextHint}
                disabled={nextHintLoading || code.length < 20}
                className="flex flex-shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-ai-border bg-ai-surface px-3.5 py-1.5 text-xs font-medium text-ai-bright transition-colors hover:bg-ai/16 disabled:cursor-not-allowed disabled:border-hairline disabled:bg-transparent disabled:text-ink-faint"
              >
                {nextHintLoading ? <><Spinner /> Analysing…</> : "Ask"}
              </button>
            </div>
            <AnimatePresence mode="wait">
              {nextHint && (
                <motion.div key="next-hint" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="mt-3 border-t border-ai-border/50 pt-3">
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-secondary">{nextHint.text}</p>
                  {nextHint.securityNote && (
                    <div className="mt-2.5 flex items-start gap-2">
                      <ShieldIcon className="mt-0.5 h-3 w-3 flex-shrink-0 text-warning-ink" />
                      <p className="text-xs leading-relaxed text-warning-ink">{nextHint.securityNote}</p>
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Per-step hint ladder — each step is its own floating card */}
          {capsLoading ? (
            <p className="text-xs text-ink-faint">Loading step hints…</p>
          ) : (
            steps.map((stepText, i) => {
              const capDepth = capDepthFor(i);
              const isActiveStep = activeStepHint?.step === i;
              return (
                <div key={i} className="elevate-1 accent-wash-green rounded-xl p-4">
                  <p className="mb-2.5 text-[13px] leading-relaxed text-ink-secondary">
                    <span className="mr-1.5 font-mono text-[11px] text-ink-faint">Step {i + 1}</span>
                    {stepText}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {LEVEL_ORDER.map((level) => {
                      const depth = LEVEL_DEPTH[level];
                      if (depth > capDepth) return null; // hidden above cap
                      const available = isAvailable(i, level);
                      const used = isUsed(i, level);
                      const isLoading = stepHintLoading?.step === i && stepHintLoading?.level === level;
                      return (
                        <button
                          key={level}
                          onClick={() => handleStepHint(i, level)}
                          disabled={!available || !!stepHintLoading}
                          className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                            used
                              ? "cursor-pointer border-ai-border bg-ai-surface text-ai-bright"
                              : available
                              ? "cursor-pointer border-hairline-strong bg-oled-2 text-ink-secondary hover:bg-oled-3"
                              : "cursor-not-allowed border-hairline bg-transparent text-ink-faint/50"
                          }`}
                        >
                          {isLoading && <Spinner />}
                          {LEVEL_LABELS[level]}
                        </button>
                      );
                    })}
                  </div>
                  <AnimatePresence mode="wait">
                    {isActiveStep && activeStepHint && (
                      <motion.div
                        key={`${activeStepHint.step}-${activeStepHint.level}`}
                        variants={revealVariants}
                        initial="initial"
                        animate="animate"
                        exit="exit"
                        className="elevate-3 mt-3 rounded-lg p-4"
                      >
                        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ai-bright">
                          {LEVEL_LABELS[activeStepHint.level as HintLevel] ?? activeStepHint.level}: Step {i + 1}
                        </p>
                        <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-secondary">{activeStepHint.text}</p>
                        {activeStepHint.securityNote && (
                          <div className="mt-2.5 flex items-start gap-2 border-t border-hairline pt-2.5">
                            <ShieldIcon className="mt-0.5 h-3 w-3 flex-shrink-0 text-warning-ink" />
                            <p className="text-xs leading-relaxed text-warning-ink">{activeStepHint.securityNote}</p>
                          </div>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })
          )}

          {/* Security hint — whole-code pass */}
          <div className="elevate-1 accent-wash-green rounded-xl p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                  <ShieldIcon className="h-3 w-3" /> Security Feedback
                </p>
                <p className="text-[13px] text-ink-faint">Analyse your whole code for security issues.</p>
              </div>
              <button
                onClick={handleSecurityHint}
                disabled={code.length < 30 || securityHintLoading}
                className="flex flex-shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-hairline-strong bg-oled-2 px-4 py-2 text-[13px] font-medium text-ink-secondary transition-colors hover:bg-oled-3 disabled:cursor-not-allowed disabled:text-ink-faint"
              >
                {securityHintLoading && <Spinner />}
                Analyse Code
              </button>
            </div>
            <AnimatePresence mode="wait">
              {securityHint && (
                <motion.div
                  key="security-hint"
                  variants={revealVariants}
                  initial="initial"
                  animate="animate"
                  exit="exit"
                  className="mt-3.5 rounded-lg border border-warning-border/60 bg-warning-surface/70 p-4"
                >
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-warning-ink">{securityHint}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Submit / annotation gate */}
        <AnimatePresence mode="wait" initial={false}>
          {!showGate ? (
            <motion.div key="submit" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="flex justify-end">
              <div className="w-[220px]">
                <Btn onClick={onShowGate} disabled={code.trim().length === 0}>Submit for Review</Btn>
              </div>
            </motion.div>
          ) : (
            <motion.div key="gate" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="elevate-2 accent-wash-green flex flex-col gap-5 rounded-xl p-6">
              <p className="text-sm font-semibold text-ink">Before submitting: answer three questions</p>

              <div>
                <label className="mb-2 block text-[13px] font-medium text-ink-secondary">1. What does your code do?</label>
                <Field value={whatCodeDoes} onChange={onWhatCodeDoes} placeholder="Briefly describe what your implementation does…" rows={3} />
              </div>

              <div>
                <label className="mb-2 block text-[13px] font-medium text-ink-secondary">2. Which threats does your code address?</label>
                <div className="mt-2 flex flex-col gap-2">
                  {threats.map((t) => (
                    <label key={t.cwe_id} className="flex cursor-pointer items-start gap-2.5">
                      <input
                        type="checkbox"
                        checked={threatsAddressed.includes(t.cwe_id)}
                        onChange={() => toggleThreat(t.cwe_id)}
                        className="mt-0.5 flex-shrink-0 accent-signal"
                      />
                      <span className="text-[13px] text-ink-secondary">
                        <span className="font-mono text-signal-bright">{t.cwe_id}</span>: {t.name}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="mb-2 block text-[13px] font-medium text-ink-secondary">
                  3. How confident are you in your code&apos;s security? (1 = low, 5 = high)
                </label>
                <div className="mt-2 flex gap-2">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      onClick={() => onConfidence(n)}
                      className={`h-10 w-10 cursor-pointer rounded-full border text-sm font-semibold transition-colors ${
                        confidence === n
                          ? "border-signal bg-signal/16 text-signal-bright"
                          : "border-hairline-strong bg-oled-2 text-ink-secondary hover:bg-oled-3"
                      }`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>

              {threats.length > 0 && (
                <div>
                  <label className="mb-2 block text-[13px] font-medium text-ink-faint">
                    Optional: which vulnerabilities do you predict the reviewer will flag?
                  </label>
                  <div className="mt-2 flex flex-col gap-2">
                    {threats.map((t) => (
                      <label key={t.cwe_id} className="flex cursor-pointer items-start gap-2.5">
                        <input
                          type="checkbox"
                          checked={predictions.includes(t.cwe_id)}
                          onChange={() => togglePrediction(t.cwe_id)}
                          className="mt-0.5 flex-shrink-0 accent-signal"
                        />
                        <span className="text-[13px] text-ink-faint">
                          <span className="font-mono text-signal-bright">{t.cwe_id}</span>: {t.name}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex justify-end">
                <div className="w-[220px]">
                  <Btn onClick={() => onFinalize(hintsLog)} disabled={!canSubmit}>Send to Code Reviewer</Btn>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>{/* end main column */}

      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      {hasSidebar && (
        <div className="sticky top-24 flex w-[300px] flex-shrink-0 flex-col gap-3">
          {plan && (
            <CollapsibleRef title="Plan" defaultOpen={true}>
              <p className="mb-2 text-xs leading-relaxed text-ink-muted">{plan.scope}</p>
              <ol className="m-0 list-decimal space-y-1 pl-4">
                {plan.steps.map((s, i) => (
                  <li key={i} className="text-xs leading-relaxed text-ink-secondary">{s}</li>
                ))}
              </ol>
            </CollapsibleRef>
          )}
          {threats.length > 0 && (
            <CollapsibleRef title="Threat Model" defaultOpen={true}>
              {threats.map((t) => (
                <div key={t.cwe_id} className="mb-3 border-b border-hairline pb-3 last:mb-0 last:border-0 last:pb-0">
                  <div className="mb-1 flex flex-wrap items-center gap-1.5">
                    <span className="font-mono text-[11px] font-semibold text-signal-bright">{t.cwe_id}</span>
                    <SeverityBadge severity={t.severity} />
                  </div>
                  <p className="mb-1 text-xs font-semibold text-ink">{t.name}</p>
                  <p className="text-[11px] leading-relaxed text-ink-muted">{t.mitigation}</p>
                </div>
              ))}
            </CollapsibleRef>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Code Review ─────────────────────────────────────────────────────────── */

function CodeReview({ findings, predictionAccuracy, plan, threats, code, onAcknowledge, onRevise }: {
  findings: ReviewFinding[];
  predictionAccuracy: number | null;
  plan: NonNullable<AgentStateData["plan"]> | null;
  threats: ThreatEntry[];
  code: string;
  onAcknowledge: () => void;
  onRevise: (newCode: string) => void;
}) {
  const [isRevising, setIsRevising] = useState(false);
  const [revisedCode, setRevisedCode] = useState(code);

  function openRevise() {
    setRevisedCode(code);
    setIsRevising(true);
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Collapsed references from earlier stages */}
      {plan && (
        <CollapsibleRef title="Plan (approved)" defaultOpen={false}>
          <ol className="m-0 list-decimal space-y-1 pl-[18px]">
            {plan.steps.map((s, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-ink-muted">{s}</li>
            ))}
          </ol>
        </CollapsibleRef>
      )}
      {threats.length > 0 && (
        <CollapsibleRef title="Threat model (approved)" defaultOpen={false}>
          {threats.map((t) => (
            <div key={t.cwe_id} className="mt-2 flex items-baseline gap-2">
              <span className="flex-shrink-0 font-mono text-[11px] font-semibold text-signal-bright">{t.cwe_id}</span>
              <span className="text-xs text-ink-muted">{t.name}</span>
            </div>
          ))}
        </CollapsibleRef>
      )}

      <SectionLabel>
        Code Review: {findings.length === 0 ? "No issues found" : `${findings.length} issue${findings.length !== 1 ? "s" : ""} found`}
      </SectionLabel>

      {predictionAccuracy !== null && (
        <div className="elevate-1 accent-wash-green rounded-xl p-5">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">Prediction Accuracy</p>
          <p className="text-sm text-ink-secondary">
            You predicted <strong className="text-ink">{Math.round(predictionAccuracy * 100)}%</strong> of the flagged vulnerabilities correctly.
          </p>
        </div>
      )}

      {findings.length === 0 ? (
        <div className="rounded-xl border border-success-deep/50 bg-success-surface/70 p-6 text-center">
          <p className="flex items-center justify-center gap-2 text-sm text-success-ink">
            <span key="ok-check" className="check-pop inline-block">✓</span>
            No security issues detected in your code.
          </p>
        </div>
      ) : (
        <motion.div variants={staggerContainer} initial="initial" animate="animate" className="flex flex-col gap-4">
          {findings.map((f, i) => (
            <motion.div key={i} variants={staggerItem} className={`${severityElevateClass(f.severity)} rounded-xl p-5`}>
              <div className="mb-3 flex flex-wrap items-center gap-2.5">
                <span className="font-mono text-[13px] font-semibold text-signal-bright">{f.cwe_id}</span>
                <SeverityBadge severity={f.severity} />
                {f.line_number && <span className="font-mono text-xs text-ink-faint">line {f.line_number}</span>}
                <span className="rounded-full border border-hairline px-1.5 py-0.5 text-[11px] text-ink-faint">{f.source}</span>
              </div>
              <p className="mb-2.5 text-[13px] leading-relaxed text-ink-secondary">{f.description}</p>
              <div className="rounded-lg bg-oled-3 p-3.5">
                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Suggested Fix</p>
                <p className="text-[13px] leading-relaxed text-ink-secondary">{f.suggested_fix}</p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Inline code editor shown when participant chooses to revise */}
      <AnimatePresence>
        {isRevising && (
          <motion.div key="revise-editor" variants={revealVariants} initial="initial" animate="animate" exit="exit" className="flex flex-col gap-2.5">
            <SectionLabel>Edit your code. Findings are shown above for reference.</SectionLabel>
            <div className="elevate-2 accent-wash-green overflow-hidden rounded-xl">
              <MonacoEditor
                height="380px"
                language="python"
                value={revisedCode}
                theme="vs-dark"
                onChange={(val) => setRevisedCode(val ?? "")}
                options={{ minimap: { enabled: false }, lineNumbers: "on", wordWrap: "on", scrollBeyondLastLine: false, fontSize: 13, padding: { top: 16, bottom: 16 } }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex justify-end gap-2.5">
        {isRevising ? (
          <>
            <button onClick={() => setIsRevising(false)} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
              Cancel
            </button>
            <div className="w-[220px]"><Btn onClick={() => onRevise(revisedCode)}>Re-submit for Review</Btn></div>
          </>
        ) : (
          <>
            {findings.length > 0 && (
              <button onClick={openRevise} className="cursor-pointer rounded-full border border-hairline-strong bg-oled-2 px-5 py-2.5 text-sm font-medium text-ink-secondary transition-all hover:bg-oled-3 hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.12)]">
                Revise Code
              </button>
            )}
            <div className="w-[220px]"><Btn variant="success" onClick={onAcknowledge}>Acknowledge and Continue</Btn></div>
          </>
        )}
      </div>
    </div>
  );
}

/* ── Task Complete ───────────────────────────────────────────────────────── */

function TaskComplete({ taskIndex, totalTasks, onNext }: {
  taskIndex: number; totalTasks: number; onNext: () => void;
}) {
  const isLast = taskIndex + 1 >= totalTasks;
  return (
    <div className="rounded-2xl border border-success-deep/50 bg-success-surface/70 p-6 text-center">
      <div className="check-pop mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-success bg-[#14532d]">
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <h2 className="mb-2 text-lg font-medium text-ink">Task {taskIndex + 1} complete</h2>
      <p className="mb-6 text-sm text-success-ink">
        {isLast ? "That was the last task." : `${totalTasks - taskIndex - 1} task${totalTasks - taskIndex - 1 !== 1 ? "s" : ""} remaining.`}
      </p>
      <div className="inline-block min-w-[200px]">
        <Btn variant={isLast ? "success" : "primary"} onClick={onNext}>
          {isLast ? "Complete Study" : "Start Next Task →"}
        </Btn>
      </div>
    </div>
  );
}

/* ── Agent error ─────────────────────────────────────────────────────────── */

function AgentError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-danger-border/60 bg-danger-surface/70 p-6">
      <p className="mb-2 text-sm font-semibold text-danger-ink">Pipeline error</p>
      <p className="mb-5 whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-red-300">{message}</p>
      <div className="inline-block min-w-[140px]">
        <Btn onClick={onRetry}>Retry Task</Btn>
      </div>
    </div>
  );
}
