"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import {
  fetchShuffledTasks,
  startSession,
  resumeSession,
  fetchStepCaps,
  requestStepHint,
  requestNextHint,
  requestSecurityHint,
  finalizeCode,
  type Task,
  type AgentStateData,
  type ThreatEntry,
  type ReviewFinding,
  type HintRecord,
  type HintLevel,
  type StepHintCap,
} from "@/lib/api";
import { FocusInput, PrimaryButton } from "@/app/page";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

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
        ? "Threat Modeller is querying NIST NVD — this can take 20–40 seconds…"
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
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "48px 24px", backgroundColor: "#030712" }}>
        <div style={{ textAlign: "center", maxWidth: "420px" }}>
          <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "52px", height: "52px", borderRadius: "50%", backgroundColor: "#052e16", border: "1px solid #15803d", marginBottom: "24px" }}>
            <svg width="22" height="22" viewBox="0 0 20 20" fill="none"><path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </div>
          <h1 style={{ fontSize: "22px", fontWeight: "700", color: "#f3f4f6", margin: "0 0 10px" }}>All {tasks.length} tasks complete</h1>
          <p style={{ fontSize: "15px", color: "#9ca3af", margin: 0 }}>Thank you for participating. You may now close this browser tab.</p>
        </div>
      </div>
    );
  }

  const currentTask = tasks[taskIndex];
  const threats = (agentState.threats ?? []) as ThreatEntry[];
  const findings = (agentState.review_findings ?? []) as ReviewFinding[];

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#030712" }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header style={{ position: "sticky", top: 0, zIndex: 10, backgroundColor: "#111827", borderBottom: "1px solid #1f2937" }}>
        <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "12px 32px" }}>
          {/* Row 1: task progress + pid */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
              <ProgressDots total={tasks.length || 4} current={taskIndex} done={uiStage === "task_complete"} />
              <span style={{ fontSize: "14px", fontWeight: "500", color: "#d1d5db" }}>
                {tasks.length > 0 ? `Task ${taskIndex + 1} of ${tasks.length}` : "Loading…"}
              </span>
            </div>
            {participantId && <span style={{ fontFamily: "monospace", fontSize: "12px", color: "#6b7280" }}>{participantId}</span>}
          </div>
          {/* Row 2: stage pills */}
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            {STAGE_LABELS.map((label, i) => {
              const allDone = uiStage === "task_complete";
              let isDone = false;
              let isActive = false;
              if (allDone) {
                isDone = true;
              } else if (uiStage === "processing" || uiStage === "finalizing") {
                const active = processingPill ?? 0;
                isDone = i < active;
                isActive = i === active;
              } else {
                const idx = stageIndex(uiStage);
                isDone = idx > i;
                isActive = idx === i;
              }
              return (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{
                    fontSize: "12px", fontWeight: "500", padding: "2px 10px", borderRadius: "9999px",
                    backgroundColor: isDone ? "#052e16" : isActive ? "#1e3a5f" : "transparent",
                    color: isDone ? "#86efac" : isActive ? "#60a5fa" : "#6b7280",
                    border: `1px solid ${isDone ? "#15803d" : isActive ? "#2563eb" : "#1f2937"}`,
                    transition: "all 0.2s ease",
                  }}>
                    {isDone ? "✓ " : ""}{label}
                  </span>
                  {i < STAGE_LABELS.length - 1 && (
                    <span style={{ color: "#374151", fontSize: "12px" }}>›</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </header>

      {/* ── Content ────────────────────────────────────────────────────────── */}
      <main style={{ maxWidth: "1080px", margin: "0 auto", padding: "32px 32px 80px" }}>

        {/* Error banner */}
        {apiError && (
          <div style={{ backgroundColor: "#450a0a", border: "1px solid #991b1b", borderRadius: "12px", padding: "16px 20px", marginBottom: "20px", display: "flex", gap: "12px", alignItems: "flex-start" }}>
            <span style={{ fontWeight: "700", color: "#f87171", flexShrink: 0 }}>✕</span>
            <p style={{ fontSize: "14px", color: "#f87171", margin: 0, flex: 1 }}>{apiError}</p>
            <button onClick={() => setApiError(null)} style={{ fontSize: "12px", color: "#9ca3af", background: "none", border: "none", cursor: "pointer" }}>dismiss</button>
          </div>
        )}

        {/* Task description (shown in all stages) */}
        {currentTask && (
          <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px 24px", marginBottom: "20px" }}>
            <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.07em", color: "#6b7280", margin: "0 0 10px" }}>Task</p>
            <p style={{ fontSize: "15px", lineHeight: "1.7", color: "#d1d5db", margin: 0, maxWidth: "72ch" }}>{currentTask.text}</p>
          </div>
        )}

        {/* Loading / processing */}
        {(uiStage === "loading" || uiStage === "starting" || uiStage === "processing" || uiStage === "finalizing") && (
          <ProcessingCard label={
            uiStage === "finalizing" ? "Code Reviewer is running…" :
            uiStage === "starting" || uiStage === "processing" ? processingLabel : "Loading…"
          } />
        )}

        {/* ── Plan Review ──────────────────────────────────────────────────── */}
        {uiStage === "plan_review" && agentState.plan && (
          <PlanReview plan={agentState.plan} history={planHistory} onDecide={handlePlanDecision} />
        )}

        {/* ── Threat Review ────────────────────────────────────────────────── */}
        {uiStage === "threat_review" && threats.length > 0 && (
          <ThreatReview threats={threats} plan={agentState.plan ?? null} onDecide={handleThreatDecision} />
        )}

        {/* ── Coding Stage ─────────────────────────────────────────────────── */}
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

        {/* ── Code Review ──────────────────────────────────────────────────── */}
        {uiStage === "code_review" && (
          <CodeReview
            findings={findings}
            predictionAccuracy={agentState.prediction_accuracy ?? null}
            plan={agentState.plan ?? null}
            threats={threats}
            onAcknowledge={handleReviewAcknowledge}
          />
        )}

        {/* ── Agent error ──────────────────────────────────────────────────── */}
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

        {/* ── Task complete ─────────────────────────────────────────────────── */}
        {uiStage === "task_complete" && (
          <TaskComplete
            taskIndex={taskIndex}
            totalTasks={tasks.length}
            onNext={handleNextTask}
          />
        )}
      </main>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────────── */

function ProgressDots({ total, current, done }: { total: number; current: number; done: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
      {Array.from({ length: total }).map((_, i) => {
        const isDone = i < current || (i === current && done);
        const isActive = i === current && !done;
        return (
          <div key={i} style={{
            height: "6px", width: isActive ? "32px" : "8px", borderRadius: "9999px",
            backgroundColor: isDone ? "#16a34a" : isActive ? "#3b82f6" : "#374151",
            transition: "background-color 0.25s ease",
          }} />
        );
      })}
    </div>
  );
}

function ProcessingCard({ label }: { label: string }) {
  const isSlowOp = label.includes("NIST") || label.includes("Threat");
  return (
    <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "32px 24px", textAlign: "center" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", marginBottom: isSlowOp ? "10px" : "0" }}>
        <Spinner />
        <span style={{ fontSize: "14px", color: "#d1d5db" }}>{label}</span>
      </div>
      {isSlowOp && (
        <p style={{ fontSize: "12px", color: "#6b7280", margin: 0 }}>
          The Threat Modeller queries the NIST NVD vulnerability database in real time — this typically takes 20–40 seconds.
        </p>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ animation: "spin 1s linear infinite" }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <circle cx="8" cy="8" r="6" stroke="#374151" strokeWidth="2" />
      <path d="M8 2a6 6 0 0 1 6 6" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = severity?.toLowerCase();
  const style: React.CSSProperties = {
    display: "inline-block", fontSize: "11px", fontWeight: "600",
    padding: "2px 8px", borderRadius: "9999px", border: "1px solid",
  };
  if (s === "critical") return <span style={{ ...style, backgroundColor: "#7f1d1d", color: "#fecaca", borderColor: "#b91c1c" }}>Critical</span>;
  if (s === "high") return <span style={{ ...style, backgroundColor: "#7c2d12", color: "#fed7aa", borderColor: "#c2410c" }}>High</span>;
  if (s === "medium") return <span style={{ ...style, backgroundColor: "#713f12", color: "#fef08a", borderColor: "#a16207" }}>Medium</span>;
  return <span style={{ ...style, backgroundColor: "#14532d", color: "#bbf7d0", borderColor: "#15803d" }}>Low</span>;
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
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <SectionLabel>
        Planner{isRevision ? ` — revision ${history.length + 1}` : ""}
      </SectionLabel>

      {/* Previous rounds */}
      {history.map((round, i) => (
        <div key={i} style={{ opacity: 0.55 }}>
          <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.07em", color: "#6b7280", margin: "0 0 8px" }}>
            Round {i + 1} — superseded
          </p>
          <div style={{ backgroundColor: "#0d1117", border: "1px solid #1f2937", borderRadius: "12px", padding: "16px 20px", marginBottom: "8px" }}>
            <p style={{ fontSize: "12px", fontWeight: "500", color: "#6b7280", margin: "0 0 8px" }}>Scope</p>
            <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#9ca3af", margin: 0 }}>{round.plan.scope}</p>
          </div>
          <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "12px 16px", display: "flex", gap: "10px", alignItems: "flex-start" }}>
            <span style={{ fontSize: "11px", fontWeight: "600", color: "#6b7280", flexShrink: 0, paddingTop: "1px" }}>Your feedback</span>
            <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#9ca3af", margin: 0, fontStyle: "italic" }}>"{round.feedback}"</p>
          </div>
        </div>
      ))}

      {/* Current plan */}
      <InfoCard title="Scope">
        <p style={{ fontSize: "14px", lineHeight: "1.7", color: "#d1d5db", margin: 0 }}>{plan.scope}</p>
      </InfoCard>

      <InfoCard title="Implementation Steps">
        <ol style={{ margin: 0, paddingLeft: "20px" }}>
          {plan.steps.map((s, i) => (
            <li key={i} style={{ fontSize: "14px", lineHeight: "1.7", color: "#d1d5db", marginBottom: "6px" }}>{s}</li>
          ))}
        </ol>
      </InfoCard>

      <InfoCard title="Security Requirements">
        <ul style={{ margin: 0, paddingLeft: "20px" }}>
          {plan.security_requirements.map((r, i) => (
            <li key={i} style={{ fontSize: "14px", lineHeight: "1.7", color: "#d1d5db", marginBottom: "6px" }}>{r}</li>
          ))}
        </ul>
      </InfoCard>

      {/* Actions */}
      {!showRevise ? (
        <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
          <button onClick={() => setShowRevise(true)} style={ghostBtnStyle}>Request Revision</button>
          <div style={{ width: "180px" }}>
            <PrimaryButton onClick={() => onDecide("approve")}>Approve Plan</PrimaryButton>
          </div>
        </div>
      ) : (
        <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
          <p style={{ fontSize: "12px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.06em", color: "#9ca3af", margin: "0 0 10px" }}>
            What would you like changed?
          </p>
          <FocusInput value={revision} onChange={setRevision} placeholder="e.g. Add input validation to the steps. Remove the caching requirement — it's out of scope." rows={3} />
          <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "12px" }}>
            <button onClick={() => { setShowRevise(false); setRevision(""); }} style={ghostBtnStyle}>Cancel</button>
            <div style={{ width: "180px" }}>
              <PrimaryButton onClick={() => { onDecide("revise", revision); setShowRevise(false); setRevision(""); }} disabled={!revision.trim()}>
                Submit Feedback
              </PrimaryButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Collapsible reference card (used in ThreatReview, CodingStage, CodeReview) ── */

function CollapsibleRef({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", overflow: "hidden" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", background: "none", border: "none", cursor: "pointer" }}
      >
        <span style={{ fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af" }}>{title}</span>
        <span style={{ color: "#6b7280", fontSize: "10px" }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && <div style={{ padding: "0 16px 14px", borderTop: "1px solid #1f2937" }}>{children}</div>}
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
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Collapsed plan reference */}
      {plan && (
        <CollapsibleRef title="Plan — approved" defaultOpen={false}>
          <ol style={{ margin: "8px 0 0", paddingLeft: "18px" }}>
            {plan.steps.map((s, i) => (
              <li key={i} style={{ fontSize: "13px", lineHeight: "1.6", color: "#9ca3af", marginBottom: "4px" }}>{s}</li>
            ))}
          </ol>
        </CollapsibleRef>
      )}

      <SectionLabel>Threat Model — {threats.length} threat{threats.length !== 1 ? "s" : ""} identified</SectionLabel>

      {threats.map((t) => (
        <div key={t.cwe_id} style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px", flexWrap: "wrap" }}>
            <span style={{ fontFamily: "monospace", fontSize: "13px", color: "#60a5fa", fontWeight: "600" }}>{t.cwe_id}</span>
            <span style={{ fontSize: "14px", fontWeight: "600", color: "#f3f4f6" }}>{t.name}</span>
            <SeverityBadge severity={t.severity} />
          </div>
          <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#9ca3af", margin: "0 0 10px" }}>{t.description}</p>
          <div style={{ backgroundColor: "#1f2937", borderRadius: "8px", padding: "12px 14px" }}>
            <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.06em", color: "#6b7280", margin: "0 0 6px" }}>Mitigation</p>
            <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#d1d5db", margin: 0 }}>{t.mitigation}</p>
          </div>
        </div>
      ))}

      {!showRevise ? (
        <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
          <button onClick={() => setShowRevise(true)} style={ghostBtnStyle}>Request Revision</button>
          <div style={{ width: "200px" }}>
            <PrimaryButton onClick={() => onDecide("approve")}>Approve Threat Model</PrimaryButton>
          </div>
        </div>
      ) : (
        <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
          <p style={{ fontSize: "12px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.06em", color: "#9ca3af", margin: "0 0 10px" }}>Revision Request</p>
          <FocusInput value={revision} onChange={setRevision} placeholder="Describe what you'd like changed…" rows={3} />
          <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end", marginTop: "12px" }}>
            <button onClick={() => setShowRevise(false)} style={ghostBtnStyle}>Cancel</button>
            <div style={{ width: "180px" }}>
              <PrimaryButton onClick={() => onDecide("revise", revision)} disabled={!revision.trim()}>Submit Revision</PrimaryButton>
            </div>
          </div>
        </div>
      )}
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
    <div style={{ display: "flex", gap: "20px", alignItems: "flex-start" }}>

      {/* ── Main column ──────────────────────────────────────────────────────── */}
      <div style={{ flex: "1 1 0", minWidth: 0, display: "flex", flexDirection: "column", gap: "16px" }}>
        <SectionLabel>Write your code — use the hints if you need help</SectionLabel>

        {/* Editor */}
        <div style={{ borderRadius: "12px", overflow: "hidden", border: "1px solid #1f2937" }}>
          <MonacoEditor
            height="380px"
            language="python"
            value={code}
            theme="vs-dark"
            onChange={(val) => onCodeChange(val ?? "")}
            options={{ minimap: { enabled: false }, lineNumbers: "on", wordWrap: "on", scrollBeyondLastLine: false, fontSize: 13, padding: { top: 16, bottom: 16 } }}
          />
        </div>

        {/* ── Hint panel ── */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <p style={{ fontSize: "11px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af", margin: 0 }}>Hints</p>

          {/* Adaptive: "What should I do next?" */}
          <div style={{ backgroundColor: "#0f172a", border: "1px solid #1e3a5f", borderRadius: "10px", padding: "14px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
              <p style={{ fontSize: "13px", color: "#93c5fd", margin: 0, fontWeight: "500" }}>What should I do next?</p>
              <button
                onClick={handleNextHint}
                disabled={nextHintLoading || code.length < 20}
                style={{
                  padding: "6px 14px", fontSize: "12px", fontWeight: "500", borderRadius: "6px",
                  border: "1px solid #1e3a5f", backgroundColor: "#1e3a5f",
                  color: code.length < 20 ? "#4b6a8c" : "#93c5fd",
                  cursor: nextHintLoading || code.length < 20 ? "not-allowed" : "pointer",
                  display: "flex", alignItems: "center", gap: "6px", flexShrink: 0,
                }}
              >
                {nextHintLoading ? <><Spinner /> Analysing…</> : "Ask"}
              </button>
            </div>
            {nextHint && (
              <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid #1e3a5f" }}>
                <p style={{ fontSize: "13px", lineHeight: "1.7", color: "#d1d5db", margin: 0, whiteSpace: "pre-wrap" }}>{nextHint.text}</p>
                {nextHint.securityNote && (
                  <div style={{ marginTop: "10px", display: "flex", gap: "8px", alignItems: "flex-start" }}>
                    <span style={{ fontSize: "11px", fontWeight: "600", color: "#60a5fa", flexShrink: 0 }}>Security</span>
                    <p style={{ fontSize: "12px", lineHeight: "1.6", color: "#93c5fd", margin: 0 }}>{nextHint.securityNote}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Per-step hint ladder */}
          {capsLoading ? (
            <p style={{ fontSize: "12px", color: "#6b7280", margin: 0 }}>Loading step hints…</p>
          ) : steps.map((stepText, i) => {
            const capDepth = capDepthFor(i);
            const isActiveStep = activeStepHint?.step === i;
            return (
              <div key={i} style={{ borderTop: "1px solid #1f2937", paddingTop: "14px" }}>
                <p style={{ fontSize: "12px", fontWeight: "500", color: "#d1d5db", margin: "0 0 10px", lineHeight: "1.5" }}>
                  <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#6b7280", marginRight: "6px" }}>Step {i + 1}</span>
                  {stepText}
                </p>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
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
                        style={{
                          padding: "6px 12px", fontSize: "12px", fontWeight: "500",
                          borderRadius: "6px",
                          border: `1px solid ${used ? "#1e3a5f" : available ? "#374151" : "#1f2937"}`,
                          backgroundColor: used ? "#1e3a5f" : available ? "#1f2937" : "transparent",
                          color: !available ? "#374151" : used ? "#60a5fa" : "#9ca3af",
                          cursor: available && !stepHintLoading ? "pointer" : "not-allowed",
                          display: "flex", alignItems: "center", gap: "5px",
                        }}
                      >
                        {isLoading && <Spinner />}
                        {LEVEL_LABELS[level]}
                      </button>
                    );
                  })}
                </div>
                {isActiveStep && activeStepHint && (
                  <div style={{ marginTop: "12px", backgroundColor: "#1f2937", borderRadius: "8px", padding: "14px 16px" }}>
                    <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.06em", color: "#6b7280", margin: "0 0 8px" }}>
                      {LEVEL_LABELS[activeStepHint.level as HintLevel] ?? activeStepHint.level} — Step {i + 1}
                    </p>
                    <p style={{ fontSize: "13px", lineHeight: "1.7", color: "#d1d5db", margin: 0, whiteSpace: "pre-wrap" }}>{activeStepHint.text}</p>
                    {activeStepHint.securityNote && (
                      <div style={{ marginTop: "10px", paddingTop: "10px", borderTop: "1px solid #374151", display: "flex", gap: "8px", alignItems: "flex-start" }}>
                        <span style={{ fontSize: "11px", fontWeight: "600", color: "#60a5fa", flexShrink: 0 }}>Security</span>
                        <p style={{ fontSize: "12px", lineHeight: "1.6", color: "#93c5fd", margin: 0 }}>{activeStepHint.securityNote}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Security hint — whole-code pass */}
        <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
            <div>
              <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af", margin: "0 0 4px" }}>Security Feedback</p>
              <p style={{ fontSize: "13px", color: "#6b7280", margin: 0 }}>Analyse your whole code for security issues.</p>
            </div>
            <button
              onClick={handleSecurityHint}
              disabled={code.length < 30 || securityHintLoading}
              style={{
                padding: "8px 16px", fontSize: "13px", fontWeight: "500", borderRadius: "8px",
                border: "1px solid #374151", backgroundColor: "#1f2937",
                color: code.length < 30 ? "#6b7280" : "#d1d5db",
                cursor: code.length < 30 || securityHintLoading ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: "6px", flexShrink: 0,
              }}
            >
              {securityHintLoading && <Spinner />}
              Analyse Code
            </button>
          </div>
          {securityHint && (
            <div style={{ marginTop: "14px", backgroundColor: "#422006", border: "1px solid #854d0e", borderRadius: "8px", padding: "14px 16px" }}>
              <p style={{ fontSize: "13px", lineHeight: "1.7", color: "#facc15", margin: 0, whiteSpace: "pre-wrap" }}>{securityHint}</p>
            </div>
          )}
        </div>

        {/* Submit / annotation gate */}
        {!showGate ? (
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <div style={{ width: "220px" }}>
              <PrimaryButton onClick={onShowGate} disabled={code.trim().length === 0}>Submit for Review</PrimaryButton>
            </div>
          </div>
        ) : (
          <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
            <p style={{ fontSize: "14px", fontWeight: "600", color: "#f3f4f6", margin: 0 }}>Before submitting — answer three questions</p>

            <div>
              <label style={gateLabelStyle}>1. What does your code do?</label>
              <FocusInput value={whatCodeDoes} onChange={onWhatCodeDoes} placeholder="Briefly describe what your implementation does…" rows={3} />
            </div>

            <div>
              <label style={gateLabelStyle}>2. Which threats does your code address?</label>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "8px" }}>
                {threats.map((t) => (
                  <label key={t.cwe_id} style={{ display: "flex", alignItems: "flex-start", gap: "10px", cursor: "pointer" }}>
                    <input type="checkbox" checked={threatsAddressed.includes(t.cwe_id)} onChange={() => toggleThreat(t.cwe_id)}
                      style={{ marginTop: "3px", accentColor: "#3b82f6", flexShrink: 0 }} />
                    <span style={{ fontSize: "13px", color: "#d1d5db" }}>
                      <span style={{ fontFamily: "monospace", color: "#60a5fa" }}>{t.cwe_id}</span> — {t.name}
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label style={gateLabelStyle}>3. How confident are you in your code's security? (1 = low, 5 = high)</label>
              <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button key={n} onClick={() => onConfidence(n)} style={{
                    width: "40px", height: "40px", borderRadius: "8px",
                    border: `1px solid ${confidence === n ? "#3b82f6" : "#374151"}`,
                    backgroundColor: confidence === n ? "#1e3a5f" : "#1f2937",
                    color: confidence === n ? "#60a5fa" : "#9ca3af",
                    fontSize: "14px", fontWeight: "600", cursor: "pointer",
                  }}>{n}</button>
                ))}
              </div>
            </div>

            {threats.length > 0 && (
              <div>
                <label style={{ ...gateLabelStyle, color: "#6b7280" }}>Optional: which vulnerabilities do you predict the reviewer will flag?</label>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "8px" }}>
                  {threats.map((t) => (
                    <label key={t.cwe_id} style={{ display: "flex", alignItems: "flex-start", gap: "10px", cursor: "pointer" }}>
                      <input type="checkbox" checked={predictions.includes(t.cwe_id)} onChange={() => togglePrediction(t.cwe_id)}
                        style={{ marginTop: "3px", accentColor: "#3b82f6", flexShrink: 0 }} />
                      <span style={{ fontSize: "13px", color: "#9ca3af" }}>
                        <span style={{ fontFamily: "monospace", color: "#60a5fa" }}>{t.cwe_id}</span> — {t.name}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <div style={{ width: "220px" }}>
                <PrimaryButton onClick={() => onFinalize(hintsLog)} disabled={!canSubmit}>Send to Code Reviewer</PrimaryButton>
              </div>
            </div>
          </div>
        )}
      </div>{/* end main column */}

      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      {hasSidebar && (
        <div style={{ width: "300px", flexShrink: 0, display: "flex", flexDirection: "column", gap: "12px", position: "sticky", top: "96px" }}>
          {plan && (
            <CollapsibleRef title="Plan" defaultOpen={true}>
              <p style={{ fontSize: "12px", color: "#9ca3af", margin: "0 0 8px", lineHeight: "1.5" }}>{plan.scope}</p>
              <ol style={{ margin: 0, paddingLeft: "16px" }}>
                {plan.steps.map((s, i) => (
                  <li key={i} style={{ fontSize: "12px", lineHeight: "1.6", color: "#d1d5db", marginBottom: "4px" }}>{s}</li>
                ))}
              </ol>
            </CollapsibleRef>
          )}
          {threats.length > 0 && (
            <CollapsibleRef title="Threat Model" defaultOpen={true}>
              {threats.map((t) => (
                <div key={t.cwe_id} style={{ marginBottom: "12px", paddingBottom: "12px", borderBottom: "1px solid #1f2937" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px", flexWrap: "wrap" }}>
                    <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#60a5fa", fontWeight: "600" }}>{t.cwe_id}</span>
                    <SeverityBadge severity={t.severity} />
                  </div>
                  <p style={{ fontSize: "12px", fontWeight: "600", color: "#f3f4f6", margin: "0 0 4px" }}>{t.name}</p>
                  <p style={{ fontSize: "11px", lineHeight: "1.55", color: "#9ca3af", margin: 0 }}>{t.mitigation}</p>
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

function CodeReview({ findings, predictionAccuracy, plan, threats, onAcknowledge }: {
  findings: ReviewFinding[];
  predictionAccuracy: number | null;
  plan: NonNullable<AgentStateData["plan"]> | null;
  threats: ThreatEntry[];
  onAcknowledge: () => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Collapsed references from earlier stages */}
      {plan && (
        <CollapsibleRef title="Plan — approved" defaultOpen={false}>
          <ol style={{ margin: "8px 0 0", paddingLeft: "18px" }}>
            {plan.steps.map((s, i) => (
              <li key={i} style={{ fontSize: "13px", lineHeight: "1.6", color: "#9ca3af", marginBottom: "4px" }}>{s}</li>
            ))}
          </ol>
        </CollapsibleRef>
      )}
      {threats.length > 0 && (
        <CollapsibleRef title="Threat model — approved" defaultOpen={false}>
          {threats.map((t) => (
            <div key={t.cwe_id} style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "8px" }}>
              <span style={{ fontFamily: "monospace", fontSize: "11px", color: "#60a5fa", fontWeight: "600", flexShrink: 0 }}>{t.cwe_id}</span>
              <span style={{ fontSize: "12px", color: "#9ca3af" }}>{t.name}</span>
            </div>
          ))}
        </CollapsibleRef>
      )}

      <SectionLabel>
        Code Review — {findings.length === 0 ? "No issues found" : `${findings.length} issue${findings.length !== 1 ? "s" : ""} found`}
      </SectionLabel>

      {predictionAccuracy !== null && (
        <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "16px 20px" }}>
          <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af", margin: "0 0 6px" }}>Prediction Accuracy</p>
          <p style={{ fontSize: "14px", color: "#d1d5db", margin: 0 }}>
            You predicted <strong style={{ color: "#f3f4f6" }}>{Math.round(predictionAccuracy * 100)}%</strong> of the flagged vulnerabilities correctly.
          </p>
        </div>
      )}

      {findings.length === 0 ? (
        <div style={{ backgroundColor: "#052e16", border: "1px solid #15803d", borderRadius: "12px", padding: "24px", textAlign: "center" }}>
          <p style={{ fontSize: "14px", color: "#86efac", margin: 0 }}>✓ No security issues detected in your code.</p>
        </div>
      ) : (
        findings.map((f, i) => (
          <div key={i} style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px", flexWrap: "wrap" }}>
              <span style={{ fontFamily: "monospace", fontSize: "13px", color: "#60a5fa", fontWeight: "600" }}>{f.cwe_id}</span>
              <SeverityBadge severity={f.severity} />
              {f.line_number && <span style={{ fontSize: "12px", color: "#6b7280", fontFamily: "monospace" }}>line {f.line_number}</span>}
              <span style={{ fontSize: "11px", color: "#6b7280", border: "1px solid #1f2937", borderRadius: "9999px", padding: "1px 6px" }}>{f.source}</span>
            </div>
            <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#d1d5db", margin: "0 0 10px" }}>{f.description}</p>
            <div style={{ backgroundColor: "#1f2937", borderRadius: "8px", padding: "12px 14px" }}>
              <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.06em", color: "#6b7280", margin: "0 0 6px" }}>Suggested Fix</p>
              <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#d1d5db", margin: 0 }}>{f.suggested_fix}</p>
            </div>
          </div>
        ))
      )}

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <div style={{ width: "220px" }}>
          <PrimaryButton variant="green" onClick={onAcknowledge}>Acknowledge and Continue</PrimaryButton>
        </div>
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
    <div style={{ backgroundColor: "#052e16", border: "1px solid #15803d", borderRadius: "12px", padding: "32px 24px", textAlign: "center" }}>
      <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: "44px", height: "44px", borderRadius: "50%", backgroundColor: "#14532d", border: "1px solid #16a34a", marginBottom: "16px" }}>
        <svg width="18" height="18" viewBox="0 0 20 20" fill="none"><path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </div>
      <h2 style={{ fontSize: "18px", fontWeight: "700", color: "#f3f4f6", margin: "0 0 8px" }}>Task {taskIndex + 1} complete</h2>
      <p style={{ fontSize: "14px", color: "#86efac", margin: "0 0 24px" }}>
        {isLast ? "That was the last task." : `${totalTasks - taskIndex - 1} task${totalTasks - taskIndex - 1 !== 1 ? "s" : ""} remaining.`}
      </p>
      <div style={{ display: "inline-block", minWidth: "200px" }}>
        <PrimaryButton variant={isLast ? "green" : "blue"} onClick={onNext}>
          {isLast ? "Complete Study" : "Start Next Task →"}
        </PrimaryButton>
      </div>
    </div>
  );
}

/* ── Shared style helpers ────────────────────────────────────────────────── */

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ backgroundColor: "#111827", border: "1px solid #1f2937", borderRadius: "12px", padding: "20px" }}>
      <p style={{ fontSize: "11px", fontWeight: "500", textTransform: "uppercase", letterSpacing: "0.07em", color: "#9ca3af", margin: "0 0 12px" }}>{title}</p>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: "13px", fontWeight: "600", color: "#d1d5db", margin: "0 0 4px" }}>{children}</p>
  );
}

function EditorSkeleton() {
  return (
    <div style={{ backgroundColor: "#1e1e1e", minHeight: "380px", padding: "20px 24px" }}>
      {[78, 62, 91, 54, 70, 45, 83, 58, 74, 49].map((w, i) => (
        <div key={i} className="skeleton" style={{ height: "14px", width: `${w}%`, borderRadius: "6px", marginBottom: "10px", animationDelay: `${i * 55}ms` }} />
      ))}
    </div>
  );
}

function AgentError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div style={{ backgroundColor: "#450a0a", border: "1px solid #991b1b", borderRadius: "12px", padding: "28px 24px" }}>
      <p style={{ fontSize: "13px", fontWeight: "600", color: "#f87171", margin: "0 0 8px" }}>Pipeline error</p>
      <p style={{ fontSize: "13px", lineHeight: "1.6", color: "#fca5a5", margin: "0 0 20px", fontFamily: "monospace" }}>{message}</p>
      <div style={{ display: "inline-block", minWidth: "140px" }}>
        <PrimaryButton onClick={onRetry}>Retry Task</PrimaryButton>
      </div>
    </div>
  );
}

const ghostBtnStyle: React.CSSProperties = {
  padding: "10px 20px", fontSize: "14px", fontWeight: "500",
  backgroundColor: "#1f2937", border: "1px solid #374151",
  borderRadius: "8px", color: "#d1d5db", cursor: "pointer",
};

const gateLabelStyle: React.CSSProperties = {
  display: "block", fontSize: "13px", fontWeight: "500", color: "#d1d5db", marginBottom: "8px",
};
