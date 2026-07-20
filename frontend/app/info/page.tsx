"use client";

import { useRouter } from "next/navigation";
import { motion } from "motion/react";

const SPRING: { type: "spring"; stiffness: number; damping: number; mass: number } = {
  type: "spring", stiffness: 130, damping: 20, mass: 1,
};

const STEPS = [
  {
    n: "01",
    title: "Enter your participant ID",
    body: "You will have been given a unique participant ID (e.g. P001) by the researcher. Enter it in the field on the home page before selecting a condition. This ID links your session to the study data. It does not identify you personally.",
  },
  {
    n: "02",
    title: "Select your assigned condition",
    body: "The researcher will tell you which condition you have been assigned to: Baseline or Multi-Agent. Click the corresponding card and then click the Enter button. If you accidentally open the wrong one, press your browser's back button and re-select.",
  },
  {
    n: "03",
    title: "Read the task carefully",
    body: "A coding task will appear at the top of the page. Read it in full before starting. The task describes what the program should do. Your goal is to write a short Python function or script that satisfies the requirements. Aim for correct, working code. Security matters too, but don't let that stop you from completing the task.",
  },
  {
    n: "04",
    title: "Use the interface to write your code",
    body: "Baseline: a GPT-4o response will be shown after a moment. You can use it as a starting point or ignore it.\n\nMulti-Agent: the pipeline will produce a plan and threat model for you to review. Approve or revise each before moving on. You then write your code in the Monaco Editor. Tiered hints are available per step. You do not have to use them. Adaptive and security hints are also available on demand.",
  },
  {
    n: "05",
    title: "Submit your code",
    body: "When you are satisfied, click Submit for Review. You will be asked three short questions (what your code does, which threats you addressed, your confidence level). Answer these honestly. They are research data, not a grade. Click Send to Code Reviewer when done.",
  },
  {
    n: "06",
    title: "Review the findings",
    body: "The Code Reviewer will analyse your code and report any security issues. You may revise your code and re-submit, or acknowledge the findings and move on. There is no penalty for findings. They are part of the measurement.",
  },
  {
    n: "07",
    title: "Complete the session",
    body: "After the Verifier runs a final check, the task is marked complete. If there is more than one task in your session, the next one will appear automatically. When all tasks are done, you will see a completion screen. You may then close the tab.",
  },
];

export default function InfoPage() {
  const router = useRouter();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#050508]">

      {/* Aurora background */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute inset-0" style={{ background: `
          radial-gradient(1px 1px at 8% 12%, rgba(255,255,255,0.85) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 19% 38%, rgba(255,255,255,0.7) 0%, transparent 100%),
          radial-gradient(1px 1px at 57% 21%, rgba(255,255,255,0.8) 0%, transparent 100%),
          radial-gradient(1px 1px at 74% 14%, rgba(255,255,255,0.75) 0%, transparent 100%),
          radial-gradient(1px 1px at 12% 75%, rgba(255,255,255,0.55) 0%, transparent 100%),
          radial-gradient(1px 1px at 88% 61%, rgba(255,255,255,0.7) 0%, transparent 100%),
          #050508
        ` }} />
        <div className="aurora-columns absolute inset-0" />
      </div>

      {/* Back nav */}
      <nav className="fixed inset-x-0 top-0 z-50 flex items-center justify-between px-8 py-5">
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 text-[13px] text-white/50 transition-colors hover:text-white"
        >
          ← Home
        </button>
        <button
          onClick={() => router.push("/faq")}
          className="text-[13px] text-white/40 transition-colors hover:text-white/70"
        >
          FAQ →
        </button>
      </nav>

      {/* Content */}
      <main className="relative z-10 mx-auto max-w-[680px] px-6 pb-24 pt-28">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={SPRING}
          className="flex flex-col gap-10"
        >
          {/* Header */}
          <div>
            <div className="mb-4 inline-block rounded-full border border-white/18 bg-white/7 px-4 py-1.5 text-[11px] font-medium uppercase tracking-widest text-white/55">
              Study instructions
            </div>
            <h1 className="text-[38px] font-bold leading-tight tracking-[-1.5px] text-white sm:text-[46px]">
              How to participate
            </h1>
            <p className="mt-4 text-[16px] leading-relaxed text-white">
              Follow the steps below. If anything is unclear, ask the researcher before you begin. Do not guess.
            </p>
          </div>

          <div className="h-px bg-white/10" />

          {/* Steps */}
          <div className="flex flex-col gap-8">
            {STEPS.map((step) => (
              <motion.div
                key={step.n}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={SPRING}
                className="flex gap-5"
              >
                <div className="flex-shrink-0 pt-0.5">
                  <span className="font-mono text-[13px] font-semibold text-white/25">{step.n}</span>
                </div>
                <div>
                  <h2 className="mb-2 text-[16px] font-semibold text-white">{step.title}</h2>
                  <div className="text-[14px] leading-relaxed text-white">
                    {step.body.split("\n\n").map((para, i) => (
                      <p key={i} className={i > 0 ? "mt-2.5" : ""}>{para}</p>
                    ))}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          <div className="h-px bg-white/10" />

          {/* Tips */}
          <div>
            <h2 className="mb-4 text-[17px] font-semibold text-white">Tips</h2>
            <ul className="flex flex-col gap-3 text-[14px] leading-relaxed text-white">
              {[
                "Write code you actually understand. Guessing at a fix you don't understand is less useful than writing something simpler that you can reason about.",
                "Use the hints if you need them. They exist for a reason and using them is not 'cheating'. The study measures outcomes, not hint usage alone.",
                "Don't spend too long on any one step. A rough working solution submitted in 15 minutes is more useful to the study than a perfect one that takes an hour.",
                "If the pipeline shows an error, click Retry Task. If it persists, let the researcher know.",
              ].map((tip, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-white/30" />
                  {tip}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              onClick={() => router.push("/faq")}
              className="rounded-full border border-white/18 bg-white/7 px-5 py-2.5 text-sm font-medium text-white/70 transition-all hover:bg-white/12 hover:text-white hover:shadow-[0_0_16px_1px_rgba(255,255,255,0.14)]"
            >
              FAQ →
            </button>
            <button
              onClick={() => router.push("/")}
              className="rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-black transition-all hover:opacity-90 hover:shadow-[0_0_20px_2px_rgba(255,255,255,0.35)]"
            >
              Back to home
            </button>
          </div>
        </motion.div>
      </main>
    </div>
  );
}
