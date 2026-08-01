"use client";

import { motion } from "motion/react";

interface Props {
  participantId: string;
  ambientClass?: string;
}

const DEBRIEF_TEXT =
  "Thank you for taking part in this study. The purpose of the research was to " +
  "investigate whether a structured multi-agent AI system produces more secure code " +
  "than a single-agent AI baseline. You were assigned to either the baseline condition " +
  "(a single AI agent) or the experimental condition (five specialised AI agents working " +
  "in sequence with you as the human overseer). We are comparing the security quality of " +
  "code produced under each condition and how participants reason about security when " +
  "working with AI tools. If you have any questions about the study, please contact " +
  "Oluwaseyi Bello at ob509@exeter.ac.uk.";

export default function DebriefPage({ participantId, ambientClass = "oled-ambient" }: Props) {
  return (
    <div className="oled-scope relative flex min-h-screen items-center justify-center px-6 py-12">
      <div className={ambientClass} />

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="relative z-10 w-full max-w-[560px]"
      >
        {/* Header */}
        <div className="mb-7 text-center">
          <div className="check-pop mx-auto mb-5 flex h-[52px] w-[52px] items-center justify-center rounded-full border border-success bg-success-surface">
            <svg width="22" height="22" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="M4 10l4.5 4.5L16 6"
                stroke="#86efac"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <h1 className="text-xl font-medium tracking-[-0.4px] text-ink">Session complete</h1>
        </div>

        {/* Participant ID — prominent so they can note it for withdrawal */}
        <div className="cosmoq-card mb-5 px-6 py-4">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Your participant ID
          </p>
          <p className="font-mono text-2xl font-semibold tracking-wide text-ink">
            {participantId}
          </p>
          <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
            Note this number if you may wish to withdraw your data within the next two weeks.
          </p>
        </div>

        {/* Debrief */}
        <div className="cosmoq-card mb-5 px-6 py-5">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Study debrief
          </p>
          <p className="text-sm leading-relaxed text-ink-secondary">{DEBRIEF_TEXT}</p>
        </div>

        {/* Withdrawal reminder */}
        <div className="rounded-2xl border border-hairline bg-oled-1 px-6 py-4">
          <p className="text-sm leading-relaxed text-ink-muted">
            If you wish to withdraw your data, contact{" "}
            <span className="text-ink-secondary">ob509@exeter.ac.uk</span> within two weeks
            quoting your participant ID.
          </p>
        </div>

        <p className="mt-6 text-center text-sm text-ink-faint">
          You may now close this browser tab.
        </p>
      </motion.div>
    </div>
  );
}
