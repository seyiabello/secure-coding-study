"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function SetupPage() {
  const [pid, setPid] = useState("");
  const [error, setError] = useState("");
  const router = useRouter();

  function handleSubmit(e: { preventDefault: () => void }) {
    e.preventDefault();
    const trimmed = pid.trim();
    if (!trimmed) {
      setError("Please enter your participant ID before continuing.");
      return;
    }
    localStorage.setItem("participant_id", trimmed);
    router.push("/study/baseline");
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        backgroundColor: "#030712",
        boxSizing: "border-box",
      }}
    >
      <div style={{ width: "100%", maxWidth: "480px" }}>
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <h1
            style={{
              fontSize: "28px",
              fontWeight: "700",
              color: "#f3f4f6",
              lineHeight: "1.3",
              margin: 0,
            }}
          >
            Secure Coding Study
          </h1>
          <p
            style={{
              marginTop: "10px",
              fontSize: "15px",
              color: "#9ca3af",
            }}
          >
            Enter your participant ID to begin the session.
          </p>
        </div>

        {/* Card */}
        <div
          style={{
            backgroundColor: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "12px",
            padding: "28px",
          }}
        >
          <form onSubmit={handleSubmit} noValidate>
            <div style={{ marginBottom: "20px" }}>
              <label
                htmlFor="pid"
                style={{
                  display: "block",
                  fontSize: "12px",
                  fontWeight: "500",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "#9ca3af",
                  marginBottom: "8px",
                }}
              >
                Participant ID
              </label>
              <FocusInput
                id="pid"
                value={pid}
                onChange={(v) => {
                  setPid(v);
                  setError("");
                }}
                placeholder="e.g. P001"
                autoFocus
              />
              {error && (
                <p
                  style={{
                    marginTop: "8px",
                    fontSize: "13px",
                    color: "#f87171",
                  }}
                >
                  {error}
                </p>
              )}
            </div>

            <PrimaryButton type="submit">Begin Study</PrimaryButton>
          </form>
        </div>

        <p
          style={{
            marginTop: "24px",
            textAlign: "center",
            fontSize: "13px",
            color: "#6b7280",
          }}
        >
          Your responses are anonymous and used for research purposes only.
        </p>
      </div>
    </div>
  );
}

/* ── Shared primitives (exported for baseline page) ─────────────────────── */

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
    padding: "11px 14px",
    fontSize: "15px",
    backgroundColor: "#1f2937",
    border: `1px solid ${focused ? "#3b82f6" : "#374151"}`,
    boxShadow: focused ? "0 0 0 1px #3b82f6" : "none",
    borderRadius: "8px",
    color: "#f3f4f6",
    outline: "none",
    boxSizing: "border-box",
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
    ? "#1f2937"
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
        padding: "12px 20px",
        fontSize: "15px",
        fontWeight: "600",
        color: disabled ? "#6b7280" : "#ffffff",
        backgroundColor: bg,
        borderRadius: "8px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background-color 0.15s",
        fontFamily: "inherit",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
    </button>
  );
}
