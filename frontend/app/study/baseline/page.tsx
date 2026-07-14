"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { fetchShuffledTasks, generateCode, type Task } from "@/lib/api";
import { FocusInput, PrimaryButton } from "@/app/page";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

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
  const [participantId, setParticipantId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskIndex, setTaskIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("loading");
  const [results, setResults] = useState<TaskResult[]>([]);
  const [notes, setNotes] = useState("");
  const [editedCode, setEditedCode] = useState("");
  const [apiError, setApiError] = useState<string | null>(null);

  const currentResult = results[taskIndex] ?? null;

  /* — init — */
  useEffect(() => {
    const pid = localStorage.getItem("participant_id");
    if (!pid) {
      router.replace("/");
      return;
    }
    setParticipantId(pid);

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
      setApiError(
        err instanceof Error ? err.message : "Generation failed. Check the backend."
      );
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
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 24px",
          backgroundColor: "#030712",
        }}
      >
        <div style={{ textAlign: "center", maxWidth: "420px" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "52px",
              height: "52px",
              borderRadius: "50%",
              backgroundColor: "#052e16",
              border: "1px solid #15803d",
              marginBottom: "24px",
            }}
          >
            <svg width="22" height="22" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M4 10l4.5 4.5L16 6" stroke="#86efac" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 style={{ fontSize: "22px", fontWeight: "700", color: "#f3f4f6", margin: "0 0 10px" }}>
            All {tasks.length} tasks complete
          </h1>
          <p style={{ fontSize: "15px", color: "#9ca3af", margin: 0 }}>
            Thank you for participating. You may now close this browser tab.
          </p>
        </div>
      </div>
    );
  }

  /* ── Main layout ─────────────────────────────────────────────────────────── */

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#030712" }}>

      {/* Progress header */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 10,
          backgroundColor: "#111827",
          borderBottom: "1px solid #1f2937",
        }}
      >
        <div
          style={{
            maxWidth: "1080px",
            margin: "0 auto",
            padding: "14px 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
            <ProgressDots
              total={tasks.length || 4}
              current={taskIndex}
              reviewing={phase === "reviewing"}
            />
            <span style={{ fontSize: "14px", fontWeight: "500", color: "#d1d5db" }}>
              {tasks.length > 0 ? `Task ${taskIndex + 1} of ${tasks.length}` : "Loading…"}
            </span>
          </div>
          {participantId && (
            <span style={{ fontFamily: "monospace", fontSize: "12px", color: "#6b7280" }}>
              {participantId}
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div
        style={{
          maxWidth: "1080px",
          margin: "0 auto",
          padding: "32px 32px 64px",
        }}
      >
        {/* Error banner */}
        {apiError && phase !== "reviewing" && (
          <div
            style={{
              backgroundColor: "#450a0a",
              border: "1px solid #991b1b",
              borderRadius: "12px",
              padding: "16px 20px",
              marginBottom: "20px",
              display: "flex",
              gap: "12px",
              alignItems: "flex-start",
            }}
          >
            <span style={{ fontSize: "14px", fontWeight: "700", color: "#f87171", flexShrink: 0 }}>✕</span>
            <p style={{ fontSize: "14px", color: "#f87171", margin: 0, whiteSpace: "pre-wrap", flex: 1 }}>
              {apiError}
            </p>
            <button
              onClick={() => setApiError(null)}
              style={{ fontSize: "12px", color: "#9ca3af", background: "none", border: "none", cursor: "pointer", flexShrink: 0 }}
            >
              dismiss
            </button>
          </div>
        )}

        {/* Loading skeleton */}
        {phase === "loading" && (
          <div
            style={{
              backgroundColor: "#111827",
              border: "1px solid #1f2937",
              borderRadius: "12px",
              padding: "24px",
            }}
          >
            <div className="skeleton" style={{ height: "12px", width: "80px", borderRadius: "6px", marginBottom: "20px" }} />
            <div className="skeleton" style={{ height: "16px", width: "100%", borderRadius: "6px", marginBottom: "10px" }} />
            <div className="skeleton" style={{ height: "16px", width: "85%", borderRadius: "6px", marginBottom: "10px" }} />
            <div className="skeleton" style={{ height: "16px", width: "70%", borderRadius: "6px" }} />
          </div>
        )}

        {/* Task card */}
        {tasks[taskIndex] && (
          <div
            style={{
              backgroundColor: "#111827",
              border: "1px solid #1f2937",
              borderRadius: "12px",
              padding: "24px",
              marginBottom: "20px",
            }}
          >
            <p
              style={{
                fontSize: "11px",
                fontWeight: "500",
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                color: "#9ca3af",
                margin: "0 0 14px",
              }}
            >
              Task {taskIndex + 1} of {tasks.length}
            </p>
            <p
              style={{
                fontSize: "15px",
                lineHeight: "1.7",
                color: "#d1d5db",
                margin: 0,
                maxWidth: "72ch",
              }}
            >
              {tasks[taskIndex].text}
            </p>
          </div>
        )}

        {/* Ready — generate button */}
        {phase === "ready" && !apiError && tasks.length > 0 && (
          <div style={{ display: "flex", justifyContent: "center", padding: "8px 0 4px" }}>
            <div style={{ width: "260px" }}>
              <PrimaryButton onClick={handleGenerate}>Generate Code</PrimaryButton>
            </div>
          </div>
        )}

        {/* Generating — skeleton */}
        {phase === "generating" && (
          <div
            style={{
              borderRadius: "12px",
              overflow: "hidden",
              border: "1px solid #1f2937",
            }}
          >
            <div
              style={{
                backgroundColor: "#111827",
                borderBottom: "1px solid #1f2937",
                padding: "12px 20px",
              }}
            >
              <div className="skeleton" style={{ height: "12px", width: "120px", borderRadius: "6px" }} />
            </div>
            <EditorSkeleton />
          </div>
        )}

        {/* Reviewing — code + notes + next */}
        {phase === "reviewing" && currentResult && (
          <>
            {/* Code card */}
            <div
              style={{
                borderRadius: "12px",
                overflow: "hidden",
                border: "1px solid #1f2937",
                marginBottom: "20px",
              }}
            >
              <div
                style={{
                  backgroundColor: "#111827",
                  borderBottom: "1px solid #1f2937",
                  padding: "12px 20px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: "500",
                    textTransform: "uppercase",
                    letterSpacing: "0.07em",
                    color: "#9ca3af",
                  }}
                >
                  Generated Code — edit if needed
                </span>
                <span style={{ fontFamily: "monospace", fontSize: "12px", color: "#6b7280" }}>
                  ⏱ {currentResult.duration.toFixed(1)}s
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

            {/* Notes card */}
            <div
              style={{
                backgroundColor: "#111827",
                border: "1px solid #1f2937",
                borderRadius: "12px",
                padding: "20px",
                marginBottom: "24px",
              }}
            >
              <label
                style={{
                  display: "block",
                  fontSize: "11px",
                  fontWeight: "500",
                  textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  color: "#9ca3af",
                  marginBottom: "10px",
                }}
              >
                Notes{" "}
                <span style={{ textTransform: "none", fontWeight: "400", color: "#6b7280" }}>
                  — optional
                </span>
              </label>
              <FocusInput
                value={notes}
                onChange={setNotes}
                placeholder="Record any observations, concerns, or thoughts about this code."
                rows={4}
              />
            </div>

            {/* Advance button */}
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <div style={{ width: "220px" }}>
                <PrimaryButton variant="green" onClick={handleNext}>
                  {taskIndex + 1 >= tasks.length ? "Complete Study" : "Next Task →"}
                </PrimaryButton>
              </div>
            </div>
          </>
        )}
      </div>
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
    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
      {Array.from({ length: total }).map((_, i) => {
        const done = i < current || (i === current && reviewing);
        const active = i === current && !reviewing;
        return (
          <div
            key={i}
            style={{
              height: "6px",
              width: active ? "32px" : "8px",
              borderRadius: "9999px",
              backgroundColor: done ? "#16a34a" : active ? "#3b82f6" : "#374151",
              transition: "background-color 0.25s ease",
            }}
          />
        );
      })}
    </div>
  );
}

function EditorSkeleton() {
  return (
    <div
      style={{
        backgroundColor: "#1e1e1e",
        minHeight: "440px",
        padding: "20px 24px",
      }}
    >
      {[78, 62, 91, 54, 70, 45, 83, 58, 74, 49, 66, 38].map((w, i) => (
        <div
          key={i}
          className="skeleton"
          style={{
            height: "14px",
            width: `${w}%`,
            borderRadius: "6px",
            marginBottom: "10px",
            animationDelay: `${i * 55}ms`,
          }}
        />
      ))}
    </div>
  );
}
