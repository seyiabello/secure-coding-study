"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { fetchShuffledTasks } from "@/lib/api";

const EASE: [number, number, number, number] = [0.16, 1, 0.3, 1];
// Critically-damped spring — matches the no-overshoot settle-in feel extracted from
// cosmoq.framer.website's load-in animation (see docs/COSMOQ_INTERACTIONS.md), used in
// place of a fixed-duration cubic-bezier for entrance-only transitions.
const SPRING_SETTLE = { type: "spring", stiffness: 130, damping: 20, mass: 1 } as const;

export default function HomePage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [pid, setPid] = useState("");
  const [pidError, setPidError] = useState("");
  const [taskCount, setTaskCount] = useState<number | null>(null);

  useEffect(() => {
    fetchShuffledTasks()
      .then((t) => setTaskCount(t.length))
      .catch(() => {});
  }, []);

  function enter(path: string) {
    const id = pid.trim();
    if (!id) {
      setPidError("Enter your participant ID first.");
      inputRef.current?.focus();
      return;
    }
    localStorage.setItem("participant_id", id);
    router.push(path);
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#050508]">

      {/* ── Aurora background ─────────────────────────────────────────── */}
      <div className="pointer-events-none fixed inset-0 z-0">
        {/* Starfield (CSS-only, no JS random) */}
        <div className="absolute inset-0" style={{ background: `
          radial-gradient(1px 1px at 8% 12%, rgba(255,255,255,0.85) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 19% 38%, rgba(255,255,255,0.7) 0%, transparent 100%),
          radial-gradient(1px 1px at 31% 8%, rgba(255,255,255,0.9) 0%, transparent 100%),
          radial-gradient(1px 1px at 44% 52%, rgba(255,255,255,0.6) 0%, transparent 100%),
          radial-gradient(1px 1px at 57% 21%, rgba(255,255,255,0.8) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 63% 67%, rgba(255,255,255,0.5) 0%, transparent 100%),
          radial-gradient(1px 1px at 74% 14%, rgba(255,255,255,0.75) 0%, transparent 100%),
          radial-gradient(1px 1px at 83% 44%, rgba(255,255,255,0.65) 0%, transparent 100%),
          radial-gradient(1px 1px at 91% 28%, rgba(255,255,255,0.8) 0%, transparent 100%),
          radial-gradient(1px 1px at 12% 75%, rgba(255,255,255,0.55) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 27% 88%, rgba(255,255,255,0.45) 0%, transparent 100%),
          radial-gradient(1px 1px at 39% 72%, rgba(255,255,255,0.7) 0%, transparent 100%),
          radial-gradient(1px 1px at 51% 83%, rgba(255,255,255,0.6) 0%, transparent 100%),
          radial-gradient(1px 1px at 68% 91%, rgba(255,255,255,0.5) 0%, transparent 100%),
          radial-gradient(1px 1px at 79% 79%, rgba(255,255,255,0.65) 0%, transparent 100%),
          radial-gradient(1px 1px at 88% 61%, rgba(255,255,255,0.7) 0%, transparent 100%),
          radial-gradient(1px 1px at 96% 85%, rgba(255,255,255,0.55) 0%, transparent 100%),
          radial-gradient(1px 1px at 5% 91%, rgba(255,255,255,0.5) 0%, transparent 100%),
          radial-gradient(1px 1px at 35% 56%, rgba(255,255,255,0.4) 0%, transparent 100%),
          radial-gradient(1.5px 1.5px at 71% 47%, rgba(255,255,255,0.6) 0%, transparent 100%),
          #050508
        ` }} />
        {/* Aurora light columns */}
        <div className="aurora-columns absolute inset-0" />
      </div>

      {/* ── Navigation ───────────────────────────────────────────────── */}
      <nav className="fixed inset-x-0 top-0 z-50 flex items-center justify-between px-8 py-5">
        <span className="text-[15px] font-bold tracking-tight text-white">
          Secure Coding Study
        </span>

        <div className="flex items-center gap-0.5 rounded-full border border-white/15 bg-black/30 px-2 py-1.5 backdrop-blur-md">
          <NavButton onClick={() => router.push("/about")}>About</NavButton>
          <NavButton onClick={() => router.push("/info")}>Study Info</NavButton>
          <NavButton onClick={() => router.push("/faq")}>FAQ</NavButton>
        </div>

        <button
          onClick={() => router.push("/about")}
          className="rounded-full border border-white/20 bg-white/10 px-5 py-2 text-sm font-medium text-white backdrop-blur-md transition-all hover:bg-white/18 hover:shadow-[0_0_20px_2px_rgba(255,255,255,0.18)]"
        >
          Learn More
        </button>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 pb-16 pt-24 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={SPRING_SETTLE}
          className="flex flex-col items-center gap-6"
        >
          <h1 className="max-w-[740px] text-[52px] font-bold leading-[1.06] tracking-[-2px] text-white sm:text-[68px] sm:tracking-[-2.5px]">
            AI-Powered<br />Secure Coding Study
          </h1>

          <p className="max-w-[480px] text-[17px] leading-relaxed text-white">
            Two ways to write secure code. Pick your condition and see how the tools shape what gets built.
          </p>

          {/* Participant ID */}
          <div className="mt-2 flex flex-col items-center gap-2">
            <div className="flex items-center gap-3">
              <motion.input
                ref={inputRef}
                type="text"
                value={pid}
                onChange={(e) => { setPid(e.target.value); setPidError(""); }}
                placeholder="Participant ID, e.g. P001"
                autoComplete="off"
                spellCheck={false}
                className={`w-[300px] rounded-full border bg-white/7 px-6 py-3 text-sm text-white backdrop-blur-sm placeholder:text-white/30 outline-none transition-all duration-150 ${
                  pidError
                    ? "border-red-500/60 focus:border-red-400 focus:ring-1 focus:ring-red-400/30"
                    : "border-white/18 focus:border-white/40 focus:ring-1 focus:ring-white/20"
                }`}
              />
            </div>

            <AnimatePresence>
              {pidError && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="text-xs text-red-400"
                >
                  {pidError}
                </motion.p>
              )}
            </AnimatePresence>

            {taskCount !== null && (
              <p className="text-[12px] text-white/60">
                {taskCount} task{taskCount !== 1 ? "s" : ""} queued for this session
              </p>
            )}
          </div>

          <motion.div
            animate={{ y: [0, 5, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="mt-2 text-white/25 text-lg"
          >
            ↓
          </motion.div>
        </motion.div>
      </section>

      {/* ── Condition cards ───────────────────────────────────────────── */}
      <section className="relative z-10 px-6 pb-24">
        <div className="mx-auto grid max-w-[1120px] grid-cols-1 gap-4 md:grid-cols-2">
          <ConditionCard
            index={0}
            visual="baseline"
            badge="Control"
            title="Baseline"
            description="Write code using a single AI response. No security guidance, no review stage. Just you, the task, and one GPT-4o reply."
            cta="Enter Baseline"
            onEnter={() => enter("/study/baseline")}
          />
          <ConditionCard
            index={1}
            visual="multiagent"
            badge="Experimental"
            title="Multi-Agent Pipeline"
            description="Work through a guided pipeline where you approve each stage. The system flags known vulnerabilities, and you write the code yourself with tiered hints available if you need them."
            cta="Enter Multi-Agent"
            onEnter={() => enter("/study/multiagent")}
          />
        </div>
        <p className="mt-8 text-center text-[12px] text-white/60">
          All responses are anonymised and used for academic research purposes only.
        </p>
      </section>

    </div>
  );
}

/* ── Nav button ──────────────────────────────────────────────────────────── */

function NavButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full px-4 py-1.5 text-[13px] text-white/65 transition-all hover:bg-white/10 hover:text-white hover:shadow-[0_0_14px_1px_rgba(255,255,255,0.14)]"
    >
      {children}
    </button>
  );
}

/* ── Condition card ──────────────────────────────────────────────────────── */

function ConditionCard({
  index,
  visual,
  badge,
  title,
  description,
  cta,
  onEnter,
}: {
  index: number;
  visual: "baseline" | "multiagent";
  badge: string;
  title: string;
  description: string;
  cta: string;
  onEnter: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 32 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING_SETTLE, delay: index * 0.1 }}
      whileHover={{ y: -5, transition: { duration: 0.22, ease: EASE } }}
      onClick={onEnter}
      className="group relative cursor-pointer overflow-hidden rounded-[22px] border border-white/10"
      style={{ height: "520px" }}
    >
      {/* Visual layer */}
      {visual === "baseline" ? <BaselineVisual /> : <MultiAgentVisual />}

      {/* Glass info box */}
      <div className="absolute inset-x-0 bottom-0 z-20 m-3 rounded-[16px] border border-white/15 bg-black/55 p-5 backdrop-blur-xl">
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/65">
          {badge}
        </div>
        <h2 className="mb-2 text-[22px] font-bold leading-tight text-white">{title}</h2>
        <p className="text-[13px] leading-relaxed text-white">{description}</p>
        <button
          onClick={(e) => { e.stopPropagation(); onEnter(); }}
          className={`mt-4 rounded-full bg-white px-5 py-2 text-[13px] font-semibold text-black transition-all hover:bg-white/90 active:scale-[0.97] ${
            visual === "baseline"
              ? "hover:shadow-[0_0_24px_4px_rgba(255,122,46,0.55)]"
              : "hover:shadow-[0_0_24px_4px_rgba(34,197,94,0.55)]"
          }`}
        >
          {cta} →
        </button>
      </div>
    </motion.div>
  );
}

/* ── Baseline visual (monitor / code editor) ─────────────────────────────── */

function BaselineVisual() {
  return (
    <div className="absolute inset-0 z-10">
      {/* Dark atmosphere */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse 70% 60% at 50% 90%, rgba(180,65,10,0.55) 0%, transparent 60%),
            radial-gradient(ellipse 55% 50% at 50% 50%, rgba(120,40,10,0.4) 0%, transparent 60%),
            linear-gradient(160deg, #0d0704 0%, #0a0807 100%)
          `,
        }}
      />
      {/* Subtle particle streaks */}
      {STREAKS.map((s, i) => (
        <div
          key={i}
          className="absolute"
          style={{
            top: s.top,
            left: s.left,
            width: s.width,
            height: "1.5px",
            transform: `rotate(${s.rot})`,
            background: i % 2 === 0
              ? "linear-gradient(90deg, transparent, rgba(255,210,80,0.7), transparent)"
              : "linear-gradient(90deg, transparent, rgba(255,110,40,0.75), transparent)",
            animation: `streak ${s.dur} ease-in-out ${s.delay} infinite`,
          }}
        />
      ))}
      {/* Code editor monitor */}
      <svg
        viewBox="0 0 280 218"
        className="absolute left-1/2 top-[6%] w-[78%] -translate-x-1/2"
        fill="none"
        aria-hidden="true"
      >
        {/* Screen glow behind monitor */}
        <ellipse cx="140" cy="105" rx="90" ry="70" fill="rgba(255,171,115,0.05)" />

        {/* Monitor outer frame */}
        <rect x="48" y="32" width="184" height="134" rx="10"
          fill="rgba(70,35,10,0.22)" stroke="rgba(255,171,115,0.48)" strokeWidth="1.5" />
        {/* Screen glass */}
        <rect x="58" y="42" width="164" height="114" rx="6"
          fill="rgba(4,4,12,0.94)" stroke="rgba(255,160,90,0.2)" strokeWidth="1" />

        {/* Window bar */}
        <rect x="58" y="42" width="164" height="13" rx="6"
          fill="rgba(10,10,24,0.98)" />
        <rect x="58" y="49" width="164" height="6" rx="0" fill="rgba(10,10,24,0.98)" />
        {/* Control dots */}
        <circle cx="72"  cy="48.5" r="3"  fill="rgba(255,88,80,0.62)" />
        <circle cx="83"  cy="48.5" r="3"  fill="rgba(255,188,50,0.62)" />
        <circle cx="94"  cy="48.5" r="3"  fill="rgba(50,210,70,0.52)" />
        {/* Tab label */}
        <rect x="108" y="45.5" width="44" height="6" rx="2" fill="rgba(255,171,115,0.2)" />

        {/* Code lines — amber = strings/values, orange = keywords, muted = comments/other */}
        {/* Line 1 — def keyword */}
        <rect x="68"  y="63" width="36" height="3.5" rx="1.5" fill="rgba(255,171,115,0.78)" />
        <rect x="108" y="63" width="52" height="3.5" rx="1.5" fill="rgba(255,185,73,0.72)" />
        <rect x="164" y="63" width="18" height="3.5" rx="1.5" fill="rgba(210,220,240,0.42)" />
        {/* Line 2 — indent + comment */}
        <rect x="80"  y="72" width="78" height="3"   rx="1.5" fill="rgba(155,165,185,0.36)" />
        {/* Line 3 — indent + if */}
        <rect x="80"  y="81" width="22" height="3.5" rx="1.5" fill="rgba(255,171,115,0.7)" />
        <rect x="106" y="81" width="48" height="3.5" rx="1.5" fill="rgba(255,185,73,0.65)" />
        <rect x="158" y="81" width="26" height="3.5" rx="1.5" fill="rgba(210,220,240,0.38)" />
        {/* Line 4 — double indent + return */}
        <rect x="92"  y="90" width="30" height="3.5" rx="1.5" fill="rgba(255,171,115,0.65)" />
        <rect x="126" y="90" width="20" height="3.5" rx="1.5" fill="rgba(210,220,240,0.36)" />
        {/* blank line gap */}
        {/* Line 6 — indent + assignment */}
        <rect x="80"  y="104" width="30" height="3.5" rx="1.5" fill="rgba(210,220,240,0.52)" />
        <rect x="114" y="104" width="14" height="3.5" rx="1.5" fill="rgba(255,171,115,0.42)" />
        <rect x="132" y="104" width="42" height="3.5" rx="1.5" fill="rgba(255,185,73,0.62)" />
        {/* Line 7 — indent + comment */}
        <rect x="80"  y="113" width="60" height="3"   rx="1.5" fill="rgba(155,165,185,0.3)" />
        {/* Line 8 — indent + long line */}
        <rect x="80"  y="122" width="95" height="3.5" rx="1.5" fill="rgba(210,220,240,0.44)" />
        {/* Line 9 — indent + return */}
        <rect x="80"  y="131" width="24" height="3.5" rx="1.5" fill="rgba(255,185,73,0.72)" />
        <rect x="108" y="131" width="36" height="3.5" rx="1.5" fill="rgba(255,171,115,0.52)" />
        {/* Cursor blink */}
        <rect x="68"  y="143" width="7"  height="3.5" rx="1"   fill="rgba(255,185,73,0.88)"
          style={{ animation: "cursor-blink 1.1s step-end infinite" }} />

        {/* Monitor stand neck */}
        <rect x="127" y="166" width="26" height="30" rx="5"
          fill="rgba(70,35,10,0.24)" stroke="rgba(255,171,115,0.38)" strokeWidth="1.3" />
        {/* Monitor base */}
        <rect x="93"  y="196" width="94" height="12" rx="6"
          fill="rgba(70,35,10,0.24)" stroke="rgba(255,171,115,0.38)" strokeWidth="1.3" />
        {/* Amber screen-glow reflection on base */}
        <ellipse cx="140" cy="196" rx="30" ry="3" fill="rgba(255,140,30,0.14)" />
      </svg>
    </div>
  );
}

const STREAKS = [
  { top: "26%", left: "28%", rot: "-48deg", width: "32px", delay: "0s",    dur: "3.8s" },
  { top: "38%", left: "64%", rot: "22deg",  width: "24px", delay: "0.8s",  dur: "4.2s" },
  { top: "58%", left: "22%", rot: "-62deg", width: "28px", delay: "1.5s",  dur: "3.5s" },
  { top: "20%", left: "52%", rot: "38deg",  width: "20px", delay: "0.4s",  dur: "4.6s" },
  { top: "68%", left: "56%", rot: "-28deg", width: "26px", delay: "1.2s",  dur: "3.9s" },
  { top: "45%", left: "78%", rot: "55deg",  width: "18px", delay: "2.0s",  dur: "4.0s" },
];

/* ── Multi-agent visual (gear/orchestration diagram) ─────────────────────── */

const GEAR_TEETH = [0, 45, 90, 135, 180, 225, 270, 315];

function MultiAgentVisual() {
  return (
    <div className="absolute inset-0 z-10">
      {/* Background gradient */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse 55% 45% at 52% 72%, rgba(215,95,18,0.7) 0%, rgba(185,72,12,0.25) 38%, transparent 60%),
            radial-gradient(ellipse 60% 50% at 64% 28%, rgba(21,175,90,0.65) 0%, rgba(24,140,80,0.22) 40%, transparent 62%),
            radial-gradient(ellipse 50% 55% at 15% 80%, rgba(20,95,55,0.45) 0%, transparent 52%),
            linear-gradient(155deg, #060610 0%, #08180f 55%, #0a0808 100%)
          `,
        }}
      />
      {/* Micro stars */}
      <div className="absolute inset-0 opacity-70" style={{ background: `
        radial-gradient(1px 1px at 14% 18%, rgba(255,255,255,0.8) 0%, transparent 100%),
        radial-gradient(1.5px 1.5px at 38% 32%, rgba(255,255,255,0.9) 0%, transparent 100%),
        radial-gradient(1px 1px at 72% 12%, rgba(255,255,255,0.7) 0%, transparent 100%),
        radial-gradient(1px 1px at 86% 44%, rgba(255,255,255,0.6) 0%, transparent 100%),
        radial-gradient(1px 1px at 55% 55%, rgba(255,255,255,0.65) 0%, transparent 100%),
        radial-gradient(1px 1px at 28% 68%, rgba(255,255,255,0.5) 0%, transparent 100%),
        radial-gradient(1px 1px at 91% 72%, rgba(255,255,255,0.45) 0%, transparent 100%)
      ` }} />

      {/* Orchestration diagram — gear (pipeline) feeding into three agents */}
      <svg
        viewBox="0 0 280 260"
        className="absolute left-1/2 top-[7%] w-[74%] -translate-x-1/2"
        fill="none"
        aria-hidden="true"
      >
        {/* Soft green glow behind gear */}
        <circle cx="140" cy="88" r="72" fill="rgba(34,197,94,0.06)" />

        {/* Connector tree */}
        <line x1="140" y1="131" x2="140" y2="158" stroke="rgba(134,239,172,0.4)" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="52"  y1="158" x2="228" y2="158" stroke="rgba(134,239,172,0.4)" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="52"  y1="158" x2="52"  y2="193" stroke="rgba(134,239,172,0.37)" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="140" y1="158" x2="140" y2="198" stroke="rgba(134,239,172,0.37)" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="228" y1="158" x2="228" y2="193" stroke="rgba(134,239,172,0.37)" strokeWidth="1.5" strokeLinecap="round" />

        {/* Junction dots — amber accent */}
        <circle cx="140" cy="158" r="3.5" fill="rgba(255,185,73,0.82)" />
        <circle cx="52"  cy="158" r="2.5" fill="rgba(255,185,73,0.58)" />
        <circle cx="228" cy="158" r="2.5" fill="rgba(255,185,73,0.58)" />

        {/* Gear outer ring */}
        <circle cx="140" cy="88" r="43" fill="rgba(34,197,94,0.08)" stroke="rgba(110,231,183,0.44)" strokeWidth="1.5" />

        {/* Gear teeth — 8 rounded rects rotated around center */}
        {GEAR_TEETH.map((deg) => (
          <rect
            key={deg}
            x="133" y="30"
            width="14" height="18"
            rx="3"
            fill="rgba(21,175,90,0.2)"
            stroke="rgba(110,231,183,0.54)"
            strokeWidth="1.4"
            transform={`rotate(${deg}, 140, 88)`}
          />
        ))}

        {/* Gear face */}
        <circle cx="140" cy="88" r="28" fill="rgba(34,197,94,0.15)" stroke="rgba(110,231,183,0.74)" strokeWidth="1.5" />
        {/* Bore ring */}
        <circle cx="140" cy="88" r="9"  fill="none" stroke="rgba(110,231,183,0.3)" strokeWidth="1" />

        {/* Person in gear center — amber/gold */}
        <circle cx="140" cy="79" r="7.5" fill="rgba(255,210,110,0.82)" />
        <path d="M 130 107 Q 130 93 140 93 Q 150 93 150 107 Z" fill="rgba(255,210,110,0.55)" />

        {/* Left agent node */}
        <circle cx="52"  cy="215" r="22" fill="rgba(34,197,94,0.1)" stroke="rgba(110,231,183,0.46)" strokeWidth="1.5" />
        <circle cx="52"  cy="207" r="5.5" fill="rgba(255,210,110,0.72)" />
        <path d="M 44 227 Q 44 216 52 216 Q 60 216 60 227 Z" fill="rgba(255,210,110,0.45)" />

        {/* Centre agent node */}
        <circle cx="140" cy="220" r="22" fill="rgba(34,197,94,0.1)" stroke="rgba(110,231,183,0.46)" strokeWidth="1.5" />
        <circle cx="140" cy="212" r="5.5" fill="rgba(255,210,110,0.72)" />
        <path d="M 132 232 Q 132 221 140 221 Q 148 221 148 232 Z" fill="rgba(255,210,110,0.45)" />

        {/* Right agent node */}
        <circle cx="228" cy="215" r="22" fill="rgba(34,197,94,0.1)" stroke="rgba(110,231,183,0.46)" strokeWidth="1.5" />
        <circle cx="228" cy="207" r="5.5" fill="rgba(255,210,110,0.72)" />
        <path d="M 220 227 Q 220 216 228 216 Q 236 216 236 227 Z" fill="rgba(255,210,110,0.45)" />
      </svg>
    </div>
  );
}
