"use client";

import { useRouter } from "next/navigation";
import { motion } from "motion/react";

const SPRING: { type: "spring"; stiffness: number; damping: number; mass: number } = {
  type: "spring", stiffness: 130, damping: 20, mass: 1,
};

export default function AboutPage() {
  const router = useRouter();

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#050508]">

      {/* Aurora background */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute inset-0" style={{ background: `
          radial-gradient(1px 1px at 8% 12%, rgba(255,255,255,0.85) 0%, transparent 100%),
          radial-gradient(1px 1px at 19% 38%, rgba(255,255,255,0.7) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 31% 8%, rgba(255,255,255,0.9) 0%, transparent 100%),
          radial-gradient(1px 1px at 57% 21%, rgba(255,255,255,0.8) 0%, transparent 100%),
          radial-gradient(1px 1px at 74% 14%, rgba(255,255,255,0.75) 0%, transparent 100%),
          radial-gradient(1px 1px at 83% 44%, rgba(255,255,255,0.65) 0%, transparent 100%),
          radial-gradient(1px 1px at 12% 75%, rgba(255,255,255,0.55) 0%, transparent 100%),
          radial-gradient(1px 1px at 68% 91%, rgba(255,255,255,0.5) 0%, transparent 100%),
          radial-gradient(1px 1px at 88% 61%, rgba(255,255,255,0.7) 0%, transparent 100%),
          #050508
        ` }} />
        <div className="aurora-columns absolute inset-0" />
      </div>

      {/* Back nav */}
      <nav className="fixed inset-x-0 top-0 z-50 px-8 py-5">
        <button
          onClick={() => router.push("/")}
          className="flex items-center gap-2 text-[13px] text-white/50 transition-colors hover:text-white"
        >
          ← Home
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
              About this study
            </div>
            <h1 className="text-[38px] font-bold leading-tight tracking-[-1.5px] text-white sm:text-[46px]">
              AI-Powered Secure Coding Study
            </h1>
          </div>

          <Divider />

          <Section title="What is this study?">
            <p>
              This study investigates whether a multi-agent AI architecture produces more secure code than a standard single-model approach.
              Participants are randomly assigned to one of two conditions and asked to complete a short coding task using the provided interface.
            </p>
            <p>
              The study is part of an MSc dissertation in Computer Science at the University of Exeter.
              It has been designed to meet the university&apos;s ethical research standards.
            </p>
          </Section>

          <Section title="What will I do?">
            <p>You will be asked to:</p>
            <ol className="mt-3 list-decimal space-y-2 pl-5">
              <li>Enter your participant ID (provided by the researcher)</li>
              <li>Choose your assigned condition: Baseline or Multi-Agent</li>
              <li>Complete one or more short Python coding tasks in the browser</li>
              <li>Submit your code when ready. The system logs your output automatically.</li>
            </ol>
            <p className="mt-4">
              Each task typically takes 10–25 minutes depending on the condition and your familiarity with Python.
              There is no right or wrong answer. The goal is to produce working, reasonably secure code using whatever assistance the interface provides.
            </p>
          </Section>

          <Section title="What are the two conditions?">
            <div className="mt-3 flex flex-col gap-4">
              <ConditionBox
                label="Baseline"
                description="A single GPT-4o call with a minimal system prompt. No security instructions are provided. You write the code yourself with no AI assistance beyond the initial response."
              />
              <ConditionBox
                label="Multi-Agent Pipeline"
                description="A five-stage human-supervised pipeline. A Planner, Threat Modeller, and Code Generator set up the context. You write the code yourself in a Monaco Editor, with optional tiered hints (direction → pseudocode → partial code). A Code Reviewer and Verifier analyse your submission."
              />
            </div>
          </Section>

          <Section title="Data and privacy">
            <p>
              All data collected is anonymised. Your participant ID is a random code. It is not linked to your name or any
              personally identifying information. The code you write and the actions you take in the interface are logged
              for research analysis only.
            </p>
            <p>
              No data is shared with third parties. Results will be published in aggregate form only as part of the
              MSc dissertation. You may withdraw at any time by closing the browser window.
            </p>
          </Section>

          <Section title="Contact">
            <p>
              This study is conducted by Seyi Bello, MSc Computer Science, University of Exeter.
              If you have questions about the study, please contact the researcher directly via your participant briefing sheet.
            </p>
          </Section>

          <div className="flex gap-3 pt-4">
            <button
              onClick={() => router.push("/info")}
              className="rounded-full border border-white/18 bg-white/7 px-5 py-2.5 text-sm font-medium text-white/70 transition-all hover:bg-white/12 hover:text-white hover:shadow-[0_0_16px_1px_rgba(255,255,255,0.14)]"
            >
              Study instructions →
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

function Divider() {
  return <div className="h-px bg-white/10" />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-[17px] font-semibold text-white">{title}</h2>
      <div className="flex flex-col gap-3 text-[15px] leading-relaxed text-white">{children}</div>
    </section>
  );
}

function ConditionBox({ label, description }: { label: string; description: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
      <p className="mb-2 text-[13px] font-semibold text-white">{label}</p>
      <p className="text-[14px] leading-relaxed text-white">{description}</p>
    </div>
  );
}
