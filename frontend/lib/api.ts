const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/* ── Shared ─────────────────────────────────────────────────────────────── */

export type Task = { task_id: string; text: string };

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j.detail) detail = j.detail; } catch { /* */ }
    throw new Error(detail);
  }
  return res.json();
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j.detail) detail = j.detail; } catch { /* */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ── Baseline ────────────────────────────────────────────────────────────── */

export type GenerateResult = {
  response: string;
  duration_seconds: number;
  logged: boolean;
};

export async function fetchShuffledTasks(): Promise<Task[]> {
  const res = await fetch(`${BASE}/tasks/shuffled`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load tasks (${res.status})`);
  return res.json();
}

export async function generateCode(params: {
  participant_id: string;
  task_id: string;
  task_order: number;
  participant_notes?: string;
}): Promise<GenerateResult> {
  return apiPost("/baseline/run", params);
}

/* ── Multi-agent types ───────────────────────────────────────────────────── */

export interface PlannerOutput {
  steps: string[];
  scope: string;
  security_requirements: string[];
}

export interface ThreatEntry {
  cwe_id: string;
  name: string;
  severity: string;
  description: string;
  mitigation: string;
}

export interface ReviewFinding {
  cwe_id: string;
  severity: string;
  description: string;
  suggested_fix: string;
  line_number: number | null;
  source: string;
}

export type HintLevel = "direction" | "pseudocode" | "partial" | "full";

export interface HintRecord {
  step_index: number;   // 0-indexed plan step; -1 for adaptive/security hints
  level: string;        // HintLevel | "adaptive" | "security"
  timestamp: string;
}

export interface StepHintCap {
  step_index: number;
  max_level: HintLevel;
  reason: string;
}

export interface AgentStateData {
  task?: string;
  current_stage?: string;
  error?: string | null;
  plan?: PlannerOutput | null;
  plan_decision?: unknown;
  threats?: ThreatEntry[] | null;
  threats_decision?: unknown;
  step_hint_caps?: StepHintCap[] | null;
  review_findings?: ReviewFinding[] | null;
  review_decision?: unknown;
  prediction_accuracy?: number | null;
  verification_result?: unknown;
}

export interface FinalizePayload {
  user_code: string;
  annotations: { what_does_code_do: string; threats_addressed: string[]; submitted_at: string };
  confidence_rating: number;
  hints_requested: HintRecord[];
  time_in_coding_seconds: number;
  pre_review_prediction?: string[];
}

/* ── Multi-agent API ─────────────────────────────────────────────────────── */

export async function startSession(params: {
  participant_id: string;
  task_id: string;
  task_order: number;
}): Promise<{ thread_id: string; state: AgentStateData }> {
  return apiPost("/session/start", params);
}

export async function resumeSession(
  threadId: string,
  stateUpdate: Record<string, unknown>
): Promise<{ state: AgentStateData }> {
  return apiPost(`/session/${threadId}/resume`, { state_update: stateUpdate });
}

export async function fetchStepCaps(
  threadId: string
): Promise<{ step_caps: StepHintCap[] }> {
  return apiGet(`/session/${threadId}/step-caps`);
}

export async function requestStepHint(
  threadId: string,
  stepIndex: number,
  level: HintLevel
): Promise<{ step_index: number; level: string; content: string; security_note: string; error: string | null }> {
  const raw = await apiPost<{
    step_index: number;
    level: string;
    content: string;
    security_note: string;
    timestamp: string;
    error: string | null;
  }>(`/session/${threadId}/hint`, { step_index: stepIndex, level });
  if (raw.error) throw new Error(raw.error);
  return raw;
}

export async function requestNextHint(
  threadId: string,
  codeSoFar: string
): Promise<{ next_step_index: number | null; status: string; content: string; security_note: string }> {
  const raw = await apiPost<{
    next_step_index: number | null;
    status: string;
    content: string;
    security_note: string;
    timestamp: string;
    error: string | null;
  }>(`/session/${threadId}/next-hint`, { code_so_far: codeSoFar });
  if (raw.error) throw new Error(raw.error);
  return raw;
}

export async function requestSecurityHint(
  threadId: string,
  codeSoFar: string
): Promise<{ hint: string }> {
  const raw = await apiPost<{
    has_issue: boolean;
    issue: string;
    suggestion: string;
    cwe_id: string | null;
    error: string | null;
  }>(`/session/${threadId}/security-hint`, { code_so_far: codeSoFar });
  if (raw.error) throw new Error(raw.error);
  if (!raw.has_issue) return { hint: "No security issues detected in your current code." };
  const cwe = raw.cwe_id ? ` (${raw.cwe_id})` : "";
  return { hint: `${raw.issue}${cwe}\n\n${raw.suggestion}` };
}

export async function finalizeCode(
  threadId: string,
  payload: FinalizePayload
): Promise<{ state: AgentStateData }> {
  return apiPost(`/session/${threadId}/finalize`, payload);
}

export async function reviseCode(
  threadId: string,
  userCode: string
): Promise<{ state: AgentStateData }> {
  return apiPost(`/session/${threadId}/revise`, { user_code: userCode });
}

/* ── Participant management ──────────────────────────────────────────────── */

export async function validateParticipant(pid: string): Promise<{
  valid: boolean;
  condition?: string;
  status?: "new" | "in_progress";
  tasks_completed?: number;
  reason?: "not_found" | "complete";
}> {
  return apiGet(`/participants/validate/${encodeURIComponent(pid)}`);
}

export async function resumeParticipantSession(pid: string): Promise<{
  condition: string;
  tasks_completed: number;
  completed_task_ids: string[];
}> {
  return apiGet(`/participants/resume/${encodeURIComponent(pid)}`);
}

export async function postConsent(params: {
  participant_id: string;
  timestamp: string;
  all_items_confirmed: boolean;
}): Promise<{ ok: boolean }> {
  return apiPost("/participants/consent", params);
}
