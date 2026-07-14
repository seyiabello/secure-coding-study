"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/* ── Pipeline metadata ───────────────────────────────────────────────────── */

const PIPELINE_STEPS = [
  { label: "Planner", detail: "Scope + security requirements" },
  { label: "Threat Modeller", detail: "RAG + NIST NVD" },
  { label: "Code Generator", detail: "HITL hints" },
  { label: "Code Reviewer", detail: "Bandit + LLM" },
  { label: "Verifier", detail: "Independent check" },
];

const BASELINE_FACTS = [
  "Single GPT-4o call — no orchestration",
  "Three-line prompt, no security instructions",
  "One response, no review or iteration",
];

/* ── Home page ───────────────────────────────────────────────────────────── */

export default function HomePage() {
  const [pid, setPid] = useState("");
  const [pidError, setPidError] = useState("");
  const router = useRouter();

  const ready = pid.trim().length > 0;

  function enter(path: string) {
    const id = pid.trim();
    if (!id) {
      setPidError("Enter your participant ID before selecting a condition.");
      return;
    }
    localStorage.setItem("participant_id", id);
    router.push(path);
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "#030712",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "56px 24px 72px",
        boxSizing: "border-box",
      }}
    >
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header
        style={{
          textAlign: "center",
          marginBottom: "44px",
          width: "100%",
          maxWidth: "860px",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "4px 12px",
            fontSize: "11px",
            fontWeight: "600",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            backgroundColor: "#0c1829",
            border: "1px solid #1e3a5f",
            borderRadius: "9999px",
            color: "#60a5fa",
            marginBottom: "18px",
          }}
        >
          <span style={{ width: "6px", height: "6px", borderRadius: "9999px", backgroundColor: "#3b82f6", display: "inline-block" }} />
          MSc Research · University of Exeter · COMM514
        </div>

        <h1
          style={{
            fontSize: "34px",
            fontWeight: "700",
            color: "#f3f4f6",
            margin: "0 0 12px",
            lineHeight: "1.2",
            letterSpacing: "-0.01em",
          }}
        >
          Secure Coding Study
        </h1>

        <p
          style={{
            fontSize: "15px",
            color: "#9ca3af",
            margin: 0,
            lineHeight: "1.65",
            maxWidth: "520px",
            marginInline: "auto",
          }}
        >
          A controlled experiment: does a structured multi-agent AI pipeline produce fewer
          security vulnerabilities than a single-model baseline?
        </p>
      </header>

      <main
        style={{
          width: "100%",
          maxWidth: "860px",
          display: "flex",
          flexDirection: "column",
          gap: "20px",
        }}
      >
        {/* ── Participant ID ──────────────────────────────────────────── */}
        <div
          style={{
            backgroundColor: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "12px",
            padding: "18px 22px",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: "16px",
              flexWrap: "wrap",
            }}
          >
            <div style={{ flexShrink: 0, paddingTop: "2px" }}>
              <p
                style={{
                  fontSize: "11px",
                  fontWeight: "600",
                  textTransform: "uppercase",
                  letterSpacing: "0.07em",
                  color: "#6b7280",
                  margin: "0 0 2px",
                }}
              >
                Participant ID
              </p>
              <p style={{ fontSize: "12px", color: "#4b5563", margin: 0 }}>
                Required
              </p>
            </div>

            <div style={{ flex: "1 1 180px", minWidth: "180px" }}>
              <FocusInput
                value={pid}
                onChange={(v) => {
                  setPid(v);
                  setPidError("");
                }}
                placeholder="e.g. P001"
                autoFocus
              />
              {pidError && (
                <p
                  style={{
                    fontSize: "12px",
                    color: "#f87171",
                    margin: "6px 0 0",
                  }}
                >
                  {pidError}
                </p>
              )}
            </div>

            <p
              style={{
                fontSize: "12px",
                color: "#4b5563",
                margin: "0",
                paddingTop: "10px",
                flexShrink: 0,
              }}
            >
              Enter your ID before selecting a condition below.
            </p>
          </div>
        </div>

        {/* ── Conditions ─────────────────────────────────────────────── */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
            gap: "16px",
            alignItems: "stretch",
          }}
        >
          {/* Baseline */}
          <ConditionPanel
            badge="Control"
            badgeStyle="neutral"
            title="Baseline"
            description="A single GPT-4o call with a three-line system prompt. No security instructions, no structured review, one response returned."
            detail={
              <ul
                style={{
                  margin: 0,
                  padding: 0,
                  listStyle: "none",
                  display: "flex",
                  flexDirection: "column",
                  gap: "7px",
                }}
              >
                {BASELINE_FACTS.map((f) => (
                  <li
                    key={f}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "8px",
                      fontSize: "13px",
                      color: "#9ca3af",
                      lineHeight: "1.5",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "10px",
                        color: "#374151",
                        marginTop: "4px",
                        flexShrink: 0,
                      }}
                    >
                      ▪
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
            }
            action={
              <GhostButton onClick={() => enter("/study/baseline")} disabled={!ready}>
                Enter Baseline
              </GhostButton>
            }
          />

          {/* Multi-agent */}
          <ConditionPanel
            badge="Experimental"
            badgeStyle="blue"
            title="Multi-Agent"
            description="Five specialised agents with human approval at each stage. Combines RAG over CWE Top 25, live CVE data from NIST NVD, Bandit static analysis, and sandboxed code execution."
            detail={
              <div>
                <p
                  style={{
                    fontSize: "11px",
                    fontWeight: "600",
                    textTransform: "uppercase",
                    letterSpacing: "0.07em",
                    color: "#4b5563",
                    margin: "0 0 10px",
                  }}
                >
                  Pipeline
                </p>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    rowGap: "10px",
                    columnGap: "0",
                  }}
                >
                  {PIPELINE_STEPS.map((step, i) => (
                    <div
                      key={step.label}
                      style={{ display: "flex", alignItems: "center" }}
                    >
                      <div>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "5px",
                            marginBottom: "2px",
                          }}
                        >
                          <div
                            style={{
                              width: "5px",
                              height: "5px",
                              borderRadius: "9999px",
                              backgroundColor: "#2563eb",
                              flexShrink: 0,
                            }}
                          />
                          <span
                            style={{
                              fontSize: "12px",
                              fontWeight: "500",
                              color: "#d1d5db",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {step.label}
                          </span>
                        </div>
                        <p
                          style={{
                            fontSize: "10px",
                            color: "#4b5563",
                            margin: "0 0 0 10px",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {step.detail}
                        </p>
                      </div>
                      {i < PIPELINE_STEPS.length - 1 && (
                        <span
                          style={{
                            fontSize: "10px",
                            color: "#1e3a5f",
                            margin: "0 7px",
                            paddingBottom: "12px",
                          }}
                        >
                          →
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            }
            action={
              <PrimaryButton onClick={() => enter("/study/multiagent")} disabled={!ready}>
                Enter Multi-Agent
              </PrimaryButton>
            }
          />
        </div>

        {/* ── Footer ─────────────────────────────────────────────────── */}
        <p
          style={{
            textAlign: "center",
            fontSize: "12px",
            color: "#374151",
            margin: "6px 0 0",
          }}
        >
          All responses are anonymised and used for academic research purposes only.
        </p>
      </main>
    </div>
  );
}

/* ── ConditionPanel ──────────────────────────────────────────────────────── */

function ConditionPanel({
  badge,
  badgeStyle,
  title,
  description,
  detail,
  action,
}: {
  badge: string;
  badgeStyle: "neutral" | "blue";
  title: string;
  description: string;
  detail: React.ReactNode;
  action: React.ReactNode;
}) {
  const [hovered, setHovered] = useState(false);

  const borderColor =
    hovered
      ? badgeStyle === "blue"
        ? "#1e3a5f"
        : "#374151"
      : "#1f2937";

  return (
    <div
      style={{
        backgroundColor: "#111827",
        border: `1px solid ${borderColor}`,
        borderRadius: "12px",
        padding: "24px",
        display: "flex",
        flexDirection: "column",
        gap: "18px",
        transition: "border-color 0.15s ease",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Badge + Title */}
      <div>
        <div style={{ marginBottom: "10px" }}>
          <span
            style={{
              padding: "3px 9px",
              fontSize: "10px",
              fontWeight: "600",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              backgroundColor:
                badgeStyle === "blue" ? "#0c1829" : "#1f2937",
              border: `1px solid ${badgeStyle === "blue" ? "#1e3a5f" : "#374151"}`,
              borderRadius: "9999px",
              color: badgeStyle === "blue" ? "#60a5fa" : "#6b7280",
            }}
          >
            {badge}
          </span>
        </div>
        <h2
          style={{
            fontSize: "22px",
            fontWeight: "700",
            color: "#f3f4f6",
            margin: "0 0 8px",
            lineHeight: "1.2",
          }}
        >
          {title}
        </h2>
        <p
          style={{
            fontSize: "13px",
            color: "#9ca3af",
            margin: 0,
            lineHeight: "1.65",
          }}
        >
          {description}
        </p>
      </div>

      {/* Detail section */}
      <div
        style={{
          backgroundColor: "#0d1420",
          border: "1px solid #1a2535",
          borderRadius: "8px",
          padding: "14px 16px",
          flex: 1,
        }}
      >
        {detail}
      </div>

      {/* Action */}
      {action}
    </div>
  );
}

/* ── Ghost button (baseline secondary action) ────────────────────────────── */

function GhostButton({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "block",
        width: "100%",
        padding: "10px 20px",
        fontSize: "14px",
        fontWeight: "500",
        color: disabled ? "#374151" : hovered ? "#d1d5db" : "#9ca3af",
        backgroundColor: disabled
          ? "transparent"
          : hovered
          ? "#1a2535"
          : "transparent",
        border: `1px solid ${disabled ? "#1f2937" : hovered ? "#374151" : "#293548"}`,
        borderRadius: "8px",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "color 0.15s ease, background-color 0.15s ease, border-color 0.15s ease",
        fontFamily: "inherit",
      }}
    >
      {children}
    </button>
  );
}

/* ── Shared primitives (exported for study pages) ────────────────────────── */

export function FocusInput({
  id,
  value,
  onChange,
  placeholder,
  autoFocus,
  rows,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  rows?: number;
}) {
  const [focused, setFocused] = useState(false);

  const sharedStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 13px",
    fontSize: "14px",
    backgroundColor: "#1f2937",
    border: `1px solid ${focused ? "#3b82f6" : "#374151"}`,
    boxShadow: focused ? "0 0 0 1px #3b82f6" : "none",
    borderRadius: "8px",
    color: "#f3f4f6",
    outline: "none",
    boxSizing: "border-box" as const,
    transition: "border-color 0.15s, box-shadow 0.15s",
    fontFamily: "inherit",
  };

  if (rows) {
    return (
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        style={{ ...sharedStyle, resize: "none", lineHeight: "1.5" }}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
    );
  }

  return (
    <input
      id={id}
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoFocus={autoFocus}
      autoComplete="off"
      spellCheck={false}
      style={sharedStyle}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
    />
  );
}

export function PrimaryButton({
  children,
  type = "button",
  onClick,
  disabled,
  variant = "blue",
}: {
  children: React.ReactNode;
  type?: "button" | "submit";
  onClick?: () => void;
  disabled?: boolean;
  variant?: "blue" | "green";
}) {
  const [hovered, setHovered] = useState(false);

  const bg = disabled
    ? "#1a2535"
    : variant === "green"
    ? hovered
      ? "#16a34a"
      : "#15803d"
    : hovered
    ? "#3b82f6"
    : "#2563eb";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "block",
        width: "100%",
        padding: "10px 20px",
        fontSize: "14px",
        fontWeight: "600",
        color: disabled ? "#4b5563" : "#ffffff",
        backgroundColor: bg,
        borderRadius: "8px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background-color 0.15s ease",
        fontFamily: "inherit",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
    </button>
  );
}
