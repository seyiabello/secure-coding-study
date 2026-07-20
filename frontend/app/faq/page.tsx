"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";

const SPRING: { type: "spring"; stiffness: number; damping: number; mass: number } = {
  type: "spring", stiffness: 130, damping: 20, mass: 1,
};
const EASE_OUT: [number, number, number, number] = [0.16, 1, 0.3, 1];

const FAQS: { q: string; a: string }[] = [
  {
    q: "Do I need to know a lot about security to participate?",
    a: "No. You only need to be comfortable writing basic Python. Security knowledge helps, but the study is designed to measure what the AI pipeline does, not to test your expertise. Write the best code you can and use the hints if you need direction.",
  },
  {
    q: "Can I use Google or documentation while writing?",
    a: "Ask the researcher before the session starts. The default is that you should use only the interface provided. This keeps the conditions consistent across participants.",
  },
  {
    q: "What if the page freezes or shows an error?",
    a: "Try refreshing the page. Your participant ID is saved in the browser (localStorage), so you won't need to re-enter it. If you're in the multi-agent condition and the pipeline shows an error after refresh, click Retry Task. If the problem persists, let the researcher know. Do not try to work around it on your own.",
  },
  {
    q: "What does 'Submit for Review' do?",
    a: "In the multi-agent condition, submitting sends your code to the Code Reviewer agent, which runs Bandit static analysis and checks against the threat model. The findings are shown to you. You can revise your code if you want, or acknowledge and move on. In the baseline condition, there is no separate review stage.",
  },
  {
    q: "Is my code kept private?",
    a: "Yes. Your code is logged under your anonymous participant ID and is only accessible to the researcher. It will not be shared publicly. The dissertation may include anonymised code excerpts as illustrative examples, but these will not be attributable to you.",
  },
  {
    q: "What happens if I don't finish in time?",
    a: "There is no hard time limit. The researcher will let you know if the session needs to wrap up. Partial submissions are still useful data. Submit whatever you have rather than leaving the editor blank.",
  },
  {
    q: "Can I withdraw after completing the session?",
    a: "Yes. You can withdraw at any point, including after the session. If you withdraw after completing a task, your data will be deleted from the study dataset. Contact the researcher within two weeks of your session to request deletion.",
  },
  {
    q: "Will I see my results or the study findings?",
    a: "The study results will be available after the dissertation is submitted (expected late 2026). If you would like to receive a summary of the findings, let the researcher know your contact preference at the end of the session.",
  },
  {
    q: "Why does the multi-agent condition take longer?",
    a: "The pipeline involves several live API calls: the Planner generates a structured implementation plan, the Threat Modeller queries the NIST NVD vulnerability database in real time (this step alone can take 20 to 40 seconds), and the Verifier runs final checks after your code is reviewed. The total pipeline overhead is typically 2 to 4 minutes before you start coding.",
  },
  {
    q: "What is the Baseline condition exactly?",
    a: "In the Baseline condition, your task is sent to GPT-4o with a minimal system prompt: no security instructions, no structured output, no review. The model's response is shown immediately. There is no pipeline. This is the control condition for the experiment.",
  },
];

export default function FAQPage() {
  const router = useRouter();
  const [open, setOpen] = useState<number | null>(null);

  function toggle(i: number) {
    setOpen((prev) => (prev === i ? null : i));
  }

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
          onClick={() => router.push("/info")}
          className="text-[13px] text-white/40 transition-colors hover:text-white/70"
        >
          ← Instructions
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
              FAQ
            </div>
            <h1 className="text-[38px] font-bold leading-tight tracking-[-1.5px] text-white sm:text-[46px]">
              Frequently asked questions
            </h1>
            <p className="mt-4 text-[16px] leading-relaxed text-white">
              If your question isn&apos;t here, ask the researcher before your session starts.
            </p>
          </div>

          <div className="h-px bg-white/10" />

          {/* Accordion */}
          <div className="flex flex-col divide-y divide-white/8">
            {FAQS.map((item, i) => (
              <div key={i}>
                <button
                  onClick={() => toggle(i)}
                  className="flex w-full cursor-pointer items-start justify-between gap-4 rounded-lg py-5 text-left transition-colors hover:bg-white/5"
                >
                  <span className="text-[15px] font-medium leading-snug text-white">{item.q}</span>
                  <motion.span
                    animate={{ rotate: open === i ? 180 : 0 }}
                    transition={{ duration: 0.2, ease: EASE_OUT }}
                    className="mt-0.5 flex-shrink-0 text-[11px] text-white/35"
                  >
                    ▼
                  </motion.span>
                </button>
                <AnimatePresence initial={false}>
                  {open === i && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.22, ease: EASE_OUT }}
                      className="overflow-hidden"
                    >
                      <p className="pb-5 text-[14px] leading-relaxed text-white">{item.a}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>

          <div className="h-px bg-white/10" />

          <div className="flex gap-3">
            <button
              onClick={() => router.push("/info")}
              className="rounded-full border border-white/18 bg-white/7 px-5 py-2.5 text-sm font-medium text-white/70 transition-all hover:bg-white/12 hover:text-white hover:shadow-[0_0_16px_1px_rgba(255,255,255,0.14)]"
            >
              ← Instructions
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
