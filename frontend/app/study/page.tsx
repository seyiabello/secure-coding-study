"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "motion/react";
import { resumeParticipantSession, validateParticipant } from "@/lib/api";
import ConsentGate from "@/components/ConsentGate";

export default function StudyPage() {
  return (
    <Suspense fallback={<LoadingShell />}>
      <StudyContent />
    </Suspense>
  );
}

function LoadingShell() {
  return (
    <div className="oled-scope flex min-h-screen items-center justify-center">
      <svg className="h-5 w-5 animate-spin text-ink-faint" viewBox="0 0 16 16" fill="none" aria-label="Loading">
        <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
        <path d="M8 2a6 6 0 0 1 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}

type Status = "loading" | "error" | "complete" | "in_progress" | "consent";

const EASE = [0.16, 1, 0.3, 1] as const;

function InfoCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="oled-scope flex min-h-screen items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.38, ease: EASE }}
        className="cosmoq-card max-w-[440px] px-8 py-8"
      >
        {children}
      </motion.div>
    </div>
  );
}

function StudyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [resuming, setResuming] = useState(false);

  const pid = searchParams.get("pid");
  const condition = searchParams.get("condition");

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!pid || !condition) {
      setErrorMsg("This study link is missing required parameters. Please contact ob509@exeter.ac.uk.");
      setStatus("error");
      return;
    }

    if (condition !== "baseline" && condition !== "multiagent") {
      setErrorMsg("Unrecognised study condition. Please use the link provided to you.");
      setStatus("error");
      return;
    }

    // Already consented this session — route directly.
    if (
      sessionStorage.getItem("consentGiven") === "true" &&
      sessionStorage.getItem("participant_id") === pid
    ) {
      router.replace(`/study/${condition}`);
      return;
    }

    validateParticipant(pid)
      .then((res) => {
        if (!res.valid) {
          if (res.reason === "complete") {
            setStatus("complete");
          } else {
            setErrorMsg(
              "This participant ID is not recognised. Please check your study link or contact ob509@exeter.ac.uk."
            );
            setStatus("error");
          }
          return;
        }

        // Condition in URL must match what the backend assigned.
        // Silently redirect rather than showing an error.
        if (res.condition && res.condition !== condition) {
          router.replace(
            `/study?pid=${encodeURIComponent(pid)}&condition=${res.condition}`
          );
          return;
        }

        sessionStorage.setItem("participant_id", pid);
        sessionStorage.setItem("condition", condition);

        setStatus(res.status === "in_progress" ? "in_progress" : "consent");
      })
      .catch(() => {
        setErrorMsg("Could not reach the study server. Make sure the backend is running on port 8000.");
        setStatus("error");
      });
  }, [pid, condition, router]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function handleContinue() {
    if (!pid || !condition) return;
    setResuming(true);
    try {
      const resume = await resumeParticipantSession(pid);
      sessionStorage.setItem("task_start_index", String(resume.tasks_completed));
    } catch {
      // Best-effort — if resume fetch fails, start from task 0.
    }
    router.push(`/study/${condition}`);
  }

  function handleStartAgain() {
    sessionStorage.removeItem("consentGiven");
    sessionStorage.removeItem("task_start_index");
    setStatus("consent");
  }

  /* ── Render ─────────────────────────────────────────────────────────────── */

  if (status === "loading") return <LoadingShell />;

  if (status === "complete") {
    return (
      <InfoCard>
        <p className="mb-2 text-center text-sm font-semibold text-ink">Study already completed</p>
        <p className="text-center text-sm leading-relaxed text-ink-muted">
          You have already completed this study. Thank you for your participation.
        </p>
        <p className="mt-4 text-center text-xs text-ink-faint">
          If you believe this is an error, contact{" "}
          <span className="text-ink-secondary">ob509@exeter.ac.uk</span> quoting your participant ID.
        </p>
      </InfoCard>
    );
  }

  if (status === "error") {
    return (
      <InfoCard>
        <p className="mb-2 text-center text-sm font-semibold text-danger-ink">Invalid study link</p>
        <p className="text-center text-sm leading-relaxed text-ink-muted">{errorMsg}</p>
      </InfoCard>
    );
  }

  if (status === "in_progress") {
    return (
      <InfoCard>
        <p className="mb-1.5 text-sm font-semibold text-ink">Session in progress</p>
        <p className="mb-6 text-sm leading-relaxed text-ink-muted">
          It looks like you started this study but did not finish. Would you like to continue where
          you left off?
        </p>
        <div className="flex flex-col gap-2.5">
          <button
            onClick={handleContinue}
            disabled={resuming}
            className="w-full cursor-pointer rounded-full bg-cosmoq-green py-3 text-sm font-semibold text-oled transition-opacity disabled:opacity-60"
          >
            {resuming ? "Loading…" : "Continue"}
          </button>
          <button
            onClick={handleStartAgain}
            disabled={resuming}
            className="w-full cursor-pointer rounded-full border border-hairline-strong bg-oled-2 py-3 text-sm font-medium text-ink-secondary transition-colors hover:bg-oled-3 disabled:opacity-60"
          >
            Start again from the consent form
          </button>
        </div>
      </InfoCard>
    );
  }

  // status === "consent"
  return (
    <ConsentGate
      participantId={pid!}
      onConsent={() => {
        sessionStorage.setItem("consentGiven", "true");
        router.push(`/study/${condition}`);
      }}
    />
  );
}
