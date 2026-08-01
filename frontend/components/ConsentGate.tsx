"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { postConsent } from "@/lib/api";

interface Props {
  participantId: string;
  onConsent: () => void;
}

/* ── Participant Information Sheet content ───────────────────────────────── */

const PIS_SECTIONS = [
  {
    heading: "Invitation and brief summary",
    body: "You are invited to take part in a research study about AI coding tools. Before you decide whether to take part, please read this information carefully. Take as much time as you need and feel free to contact the researcher if you have any questions.",
  },
  {
    heading: "Purpose of the research",
    body: "AI tools that help developers write code are becoming increasingly common. However, research has shown that these tools often produce code with security weaknesses. This study investigates whether using a structured system of multiple AI agents working in sequence, with a human reviewing each step, produces more secure code than a single AI agent working alone. The results will contribute to understanding how AI coding tools can be designed more safely.",
  },
  {
    heading: "Why have I been approached?",
    body: "You have been invited because you are a computer science or software engineering student at the University of Exeter with experience writing Python code. We are aiming to recruit a minimum of 52 participants in total, split across two conditions of 26 participants each.",
  },
  {
    heading: "What would taking part involve?",
    body: "If you agree to take part, you will complete four short coding tasks using an AI-assisted interface accessed through a web browser. Each task asks you to write a Python function. You will use an AI tool built into the interface to help you. The session will take approximately 30 to 45 minutes and can be completed at a time and place that suits you.\n\nYour session will be assigned a participant number (for example, P01). The system will automatically log your participant number, the task you submitted, the AI output, and the time taken. No names or personal details are collected or stored at any point.\n\nTask order is randomised across participants. You will complete all four tasks in a single session.",
  },
  {
    heading: "What are the possible benefits of taking part?",
    body: "There is no direct personal benefit to you from taking part. The broader benefit is contributing to research that may help make AI coding tools safer and more effective for developers.",
  },
  {
    heading: "What are the possible disadvantages and risks of taking part?",
    body: "There are no significant risks to taking part. The tasks involve standard programming activities and should not cause distress. If at any point you feel uncomfortable, you are free to stop without giving a reason and without any consequences.",
  },
  {
    heading: "What will happen if I do not want to carry on with the study?",
    body: "Your participation is entirely voluntary. You can stop at any time during the session by closing the browser window. You may also withdraw after completing the session by contacting the researcher at ob509@exeter.ac.uk within two weeks of your session, quoting your participant ID number. If you withdraw, your session data will be deleted and will not be used in the analysis. There are no negative consequences for withdrawing.\n\nPlease note that after the two-week window, the researcher will remove the record that links participant ID numbers to session dates. At that point there is no longer any way to identify which session log belongs to which participant, and withdrawal of data will not be possible. This is why the two-week window exists. Your participant ID number is shown to you at the start of your session and you should make a note of it if you think you may wish to withdraw later.",
  },
  {
    heading: "How will my information be kept confidential?",
    body: "The University of Exeter processes personal data for the purposes of carrying out research in the public interest. If you have any queries about the University's processing of your personal data that cannot be resolved by the research team, further information may be obtained from the University's Data Protection Officer by emailing informationgovernance@exeter.ac.uk.\n\nYour session data is identified only by a participant number. No names, email addresses, or any other personal details are stored alongside session data. Session log files are stored on the University of Exeter OneDrive account held by the project supervisor, which requires university login credentials to access. Only the researcher and supervisor have access to this data. Data will be retained for five years after the end of the project in line with University retention schedules, after which it will be permanently deleted. Anonymised data may be shared as a supplementary dataset if the research is published.\n\nThere are no circumstances in this study where confidentiality would need to be broken.",
  },
  {
    heading: "Will I receive any payment for taking part?",
    body: "Participation is voluntary and unpaid. No course credits, vouchers, or gifts are offered.",
  },
  {
    heading: "What will happen to the results of this study?",
    body: "Results will be written up as part of an MSc dissertation submitted to the University of Exeter. The research may also be written up for academic publication. Only aggregated and anonymised results will be reported. No individual participant's data will be identifiable in any output. If you would like to be informed of the results, please contact the researcher after you have taken part.",
  },
  {
    heading: "Who is organising and funding this study?",
    body: "This study is organised by Oluwaseyi Bello as part of an MSc research project supervised by Professor Solomon Oyelere at the University of Exeter. The sponsor for this study is the University of Exeter. The study is not externally funded.",
  },
  {
    heading: "Who has reviewed this study?",
    body: "This project has been reviewed by the University of Exeter Engineering, Mathematics and Physical Sciences Research Ethics Committee (Application ID: 13362509).",
  },
];

/* ── Consent checklist items — exact wording from Consent Form v1.0 ─────── */

const CONSENT_ITEMS = [
  "I confirm that I have read the Participant Information Sheet (Version 1.0, dated 18/06/2026) for the above project. I have had the opportunity to consider the information and ask questions.",
  "I understand that my participation is voluntary and that I am free to withdraw at any time without giving any reason and without any negative consequences.",
  "I understand that relevant sections of the data collected during the study may be seen by the researcher and supervisor, and by members of the University of Exeter Research Ethics Committee where relevant.",
  "I understand that taking part involves completing coding tasks using an AI interface. My session data (participant ID, task submitted, AI output, and time taken) will be logged anonymously and used for the purposes of academic analysis.",
  "I understand that my data will be fully anonymised using a participant number and that no names or personal details will be stored at any point.",
  "I understand that because my data is fully anonymised, it will not be possible to withdraw my data after two weeks from the date of my session, as it will no longer be possible to identify which data belongs to me.",
  "I understand that anonymised session data may be shared with other researchers or made available as a supplementary dataset if the research is published.",
  "I agree to take part in the above study.",
];

/* ── Component ───────────────────────────────────────────────────────────── */

export default function ConsentGate({ participantId, onConsent }: Props) {
  const [checked, setChecked] = useState<boolean[]>(Array(CONSENT_ITEMS.length).fill(false));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allChecked = checked.every(Boolean);

  function toggle(i: number) {
    setChecked((prev) => {
      const next = [...prev];
      next[i] = !next[i];
      return next;
    });
  }

  async function handleProceed() {
    if (!allChecked || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await postConsent({
        participant_id: participantId,
        timestamp: new Date().toISOString(),
        all_items_confirmed: true,
      });
      onConsent();
    } catch {
      setError("Could not record your consent. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="oled-scope min-h-screen">
      <div className="cosmoq-ambient" />

      <div className="relative z-10 mx-auto max-w-[680px] px-5 py-12 pb-24">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.38, ease: [0.16, 1, 0.3, 1] }}
        >
          {/* ── PIS ─────────────────────────────────────────────────────── */}
          <div className="cosmoq-card overflow-hidden">
            {/* PIS header */}
            <div className="border-b border-hairline px-7 py-5">
              <p className="text-[11px] font-medium uppercase tracking-wider text-ink-faint">
                Version 2.0 · 18/06/2026
              </p>
              <h1 className="mt-1.5 text-lg font-semibold tracking-tight text-ink">
                Participant Information Sheet
              </h1>
              <div className="mt-3 space-y-1">
                <p className="text-sm leading-relaxed text-ink-secondary">
                  <span className="font-medium text-ink">Title of Project:</span>{" "}
                  Human-Orchestrated Multi-Agent AI Systems for Secure Code Generation: A Controlled Experiment
                </p>
                <p className="text-sm text-ink-muted">
                  <span className="font-medium text-ink-secondary">Researcher:</span>{" "}
                  Oluwaseyi Bello, MSc Computer Science, University of Exeter
                </p>
                <p className="text-sm text-ink-muted">
                  <span className="font-medium text-ink-secondary">Supervisor:</span>{" "}
                  Professor Solomon Oyelere, Department of Computer Science, University of Exeter
                </p>
              </div>
            </div>

            {/* PIS body */}
            <div className="px-7 py-6">
              <div className="space-y-5">
                {PIS_SECTIONS.map((s) => (
                  <div key={s.heading}>
                    <h2 className="mb-1.5 text-sm font-semibold text-ink">{s.heading}</h2>
                    {s.body.split("\n\n").map((para, j) => (
                      <p key={j} className="mb-2 text-sm leading-relaxed text-ink-muted last:mb-0">
                        {para}
                      </p>
                    ))}
                  </div>
                ))}

                {/* Contact section */}
                <div>
                  <h2 className="mb-1.5 text-sm font-semibold text-ink">
                    Contact for questions or requests regarding your participation
                  </h2>
                  <p className="mb-2 text-sm leading-relaxed text-ink-muted">
                    If you have any questions before, during, or after the study, please contact:
                  </p>
                  <p className="mb-1 text-sm text-ink-muted">
                    Oluwaseyi Bello · Email:{" "}
                    <span className="text-ink-secondary">ob509@exeter.ac.uk</span>
                  </p>
                  <p className="mb-1 text-sm text-ink-muted">
                    To contact the Research Ethics Committee, please email Professor Mark Kelson:{" "}
                    <span className="text-ink-secondary">m.j.kelson@exeter.ac.uk</span>
                  </p>
                  <p className="mb-3 text-sm leading-relaxed text-ink-muted">
                    To make a complaint or comment, please contact the University Research Ethics and
                    Governance Team: cgr-reg@exeter.ac.uk · Dr Sean Jennings, Head of Research
                    Governance, Ethics and Compliance, University Research Services, University of
                    Exeter, Innovation Centre, Rennes Drive, Exeter, EX4 4RN · Tel: 01392 726621
                  </p>
                  <p className="text-sm text-ink-faint">Thank you for your interest in this project.</p>
                </div>
              </div>
            </div>
          </div>

          {/* ── Consent form ─────────────────────────────────────────────── */}
          <div className="mt-8">
            <div className="mb-1 flex items-center gap-3">
              <div className="h-px flex-1 bg-hairline" />
              <h2 className="text-sm font-semibold text-ink">Before you begin</h2>
              <div className="h-px flex-1 bg-hairline" />
            </div>
            <p className="mb-5 mt-3 text-center text-sm text-ink-muted">
              Please read and tick each statement before continuing.
            </p>

            <div className="space-y-2.5">
              {CONSENT_ITEMS.map((item, i) => (
                <label
                  key={i}
                  className={`flex cursor-pointer items-start gap-4 rounded-2xl border px-5 py-4 transition-all duration-150 ${
                    checked[i]
                      ? "border-cosmoq-green/40 bg-cosmoq-green-tint"
                      : "border-hairline bg-oled-1 hover:border-hairline-strong"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={checked[i]}
                    onChange={() => toggle(i)}
                  />
                  {/* Custom checkbox */}
                  <div
                    aria-hidden="true"
                    className={`mt-0.5 flex h-[18px] w-[18px] flex-shrink-0 items-center justify-center rounded border transition-all duration-150 ${
                      checked[i]
                        ? "border-cosmoq-green bg-cosmoq-green"
                        : "border-hairline-strong bg-oled-3"
                    }`}
                  >
                    {checked[i] && (
                      <svg width="11" height="11" viewBox="0 0 11 11" fill="none" aria-hidden="true">
                        <path
                          d="M1.5 5.5l2.5 2.5L9.5 2.5"
                          stroke="#000"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </div>
                  <span className="text-sm leading-relaxed text-ink-secondary">{item}</span>
                </label>
              ))}
            </div>

            {/* Progress */}
            <p className="mt-4 text-center text-xs text-ink-faint">
              {checked.filter(Boolean).length} of {CONSENT_ITEMS.length} items confirmed
            </p>

            {/* Error */}
            {error && (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-danger-border/60 bg-danger-surface/70 px-4 py-3 text-sm text-danger-ink"
              >
                {error}
              </p>
            )}

            {/* Proceed button */}
            <div className="mt-6">
              <button
                onClick={handleProceed}
                disabled={!allChecked || submitting}
                className={`w-full rounded-full py-3.5 text-sm font-semibold transition-all duration-150 ${
                  allChecked && !submitting
                    ? "cosmoq-pill-green cursor-pointer bg-cosmoq-green text-oled"
                    : "cursor-not-allowed bg-oled-3 text-ink-faint"
                }`}
              >
                {submitting ? "Recording consent…" : "I agree and wish to continue"}
              </button>
            </div>

            {/* Participant ID */}
            <p className="mt-5 text-center text-xs text-ink-faint">
              Participant ID:{" "}
              <span className="font-mono text-ink-muted">{participantId}</span>
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
