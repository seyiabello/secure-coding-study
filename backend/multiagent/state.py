"""
multiagent/state.py
-------------------
Shared LangGraph state schema for the multi-agent system.

This is the contract every agent depends on. Write this before any agent.

The state is passed between all five agents (Planner, Threat Modeller,
Code Generator, Code Reviewer, Verifier) and the human participant.
Each agent reads the current state and returns a dict of updates.
LangGraph merges those updates into the existing state automatically.

All fields except the session-start fields are Optional because the state
is populated progressively — early agents cannot know what later agents
will produce.
"""

import datetime
from typing import Optional, TypedDict

from config import MODEL, TEMPERATURE


# =============================================================================
# Sub-schemas
# Each TypedDict below defines the structure of one section of the full state.
# Using named types makes the agent code easier to read and type-check.
# =============================================================================

class PlannerOutput(TypedDict):
    """
    What the Planner agent produces.

    steps               — the coding task broken into ordered sub-tasks
    scope               — a sentence describing what the code should and
                          should not do (boundaries of the implementation)
    security_requirements — security properties the code must satisfy,
                            identified by the Planner before any code is written
    """
    steps: list[str]
    scope: str
    security_requirements: list[str]


class ThreatEntry(TypedDict):
    """
    One threat identified by the Threat Modeller.

    cwe_id      — e.g. "CWE-89" — the official MITRE identifier
    name        — short human-readable name of the weakness
    severity    — "Critical", "High", or "Medium"
    description — how this threat applies to the specific task
    mitigation  — what the Code Generator should do to prevent it
    """
    cwe_id: str
    name: str
    severity: str
    description: str
    mitigation: str


class ReviewFinding(TypedDict):
    """
    One security issue found by the Code Reviewer.

    cwe_id        — the CWE this finding maps to
    severity      — "Critical", "High", or "Medium"
    description   — what the issue is and where it appears in the code
    suggested_fix — a concrete recommendation to resolve the issue
    line_number   — optional line number if identifiable from the code
    source        — "bandit" if flagged by static analysis, "llm" if by review
    """
    cwe_id: str
    severity: str
    description: str
    suggested_fix: str
    line_number: Optional[int]
    source: str


class ThreatCheckResult(TypedDict):
    """
    The Verifier's verdict on one threat from the threat model.

    cwe_id  — the threat being checked
    passed  — True if the final code adequately mitigates this threat
    notes   — explanation of why it passed or failed
    """
    cwe_id: str
    passed: bool
    notes: str


class ExecutionResult(TypedDict):
    """
    Result of running the generated code in the sandbox.

    passed   — True if the code executed without errors
    stdout   — captured standard output (truncated if very long)
    stderr   — captured standard error output
    exit_code — the process exit code (0 = success)
    """
    passed: bool
    stdout: str
    stderr: str
    exit_code: int


class VerificationResult(TypedDict):
    """
    The Verifier agent's complete output.

    overall_pass   — True only if all threats passed AND execution passed
    threats_checked — per-threat verdict from the Verifier
    bandit_findings — independent Bandit run results (separate from Reviewer)
    execution_result — sandbox execution result
    notes           — overall summary from the Verifier
    """
    overall_pass: bool
    threats_checked: list[ThreatCheckResult]
    bandit_findings: list[dict]
    execution_result: ExecutionResult
    notes: str


class ParticipantDecision(TypedDict):
    """
    The human participant's decision at one stage of the pipeline.

    action           — one of "approve", "revise", or "override"
                       approve  = accept the agent's output and move on
                       revise   = modify the agent's output before moving on
                       override = completely replace the agent's output
    revised_content  — the participant's replacement text if action is
                       "revise" or "override"; None if action is "approve"
    timestamp        — ISO 8601 UTC timestamp of when the decision was made
    """
    action: str
    revised_content: Optional[str]
    timestamp: str


class HintRecord(TypedDict):
    """
    One hint request made by the participant during the coding stage.

    step_index — which plan step the hint was for (0-indexed); -1 for adaptive hints
    level      — "direction" | "pseudocode" | "partial" | "full" | "adaptive" | "security"
    timestamp  — ISO 8601 UTC when the hint was requested
    """
    step_index: int
    level: str
    timestamp: str


class StepHintCap(TypedDict):
    """
    The maximum hint level available for one plan step.

    Computed once after the threat model is approved by running the step
    classifier, which matches each step against threat model mitigations.

    step_index — 0-indexed position of the step in plan.steps
    max_level  — highest level the participant may request for this step:
                 "direction"  — plain English only (step directly implements a mitigation)
                 "pseudocode" — up to comment-only skeleton
                 "partial"    — up to partial implementation with TODOs
                 "full"       — full implementation (boilerplate steps only)
    reason     — why this cap was assigned (for logging/transparency)
    """
    step_index: int
    max_level: str
    reason: str


class CodingAnnotations(TypedDict):
    """
    Participant's annotation gate answers. Required before submitting code for review.

    what_does_code_do  — free-text explanation of what their code does
    threats_addressed  — list of threats they believe their code mitigates
    submitted_at       — ISO 8601 UTC when the annotation gate was submitted
    """
    what_does_code_do: str
    threats_addressed: list[str]
    submitted_at: str


class HitlCodingMetrics(TypedDict):
    """
    All human-in-the-loop metrics collected during the coding stage.

    hint_depth_reached      — deepest hint level used across all steps
                              (direction=1, pseudocode=2, partial=3, full=4, 0=none)
    hints_requested         — ordered list of every hint request with timestamp
    time_in_coding_seconds  — total seconds spent at the coding stage
    confidence_rating       — participant self-assessed confidence 1 (low) to 5 (high)
    annotations             — annotation gate answers (what code does, which threats addressed)
    """
    hint_depth_reached: int
    hints_requested: list[HintRecord]
    time_in_coding_seconds: float
    confidence_rating: int
    annotations: Optional[CodingAnnotations]


# =============================================================================
# Full state schema
# =============================================================================

class AgentState(TypedDict):
    """
    The complete shared state for one multi-agent session.

    Agents receive this full state and return a dict containing only the
    fields they update. LangGraph merges those partial updates back in.

    Fields are grouped by which part of the pipeline populates them.
    All agent output fields are Optional because the state is built up
    progressively — no agent knows what comes after it.
    """

    # ── Session metadata ──────────────────────────────────────────────────────
    # Set when the session starts. Never modified by agents.

    participant_id: str
    # Who is running this session. e.g. "P01". Used in the log record.

    task: str
    # The coding task as submitted by the participant. Unchanged throughout.

    condition: str
    # Always "multiagent" for this state. Used in the log schema to
    # distinguish from baseline sessions.

    task_id: Optional[str]
    # e.g. "T1", "T2". Identifies which coding task this session used.

    task_order: Optional[int]
    # 1–4. The position this task appeared in the participant's randomised sequence.
    # Required covariate for statistical analysis — controls for learning effects.

    session_start: str
    # ISO 8601 UTC timestamp set when the session begins.

    session_end: Optional[str]
    # Set when the session completes (after Verifier finishes).

    duration_seconds: Optional[float]
    # Total session time. Calculated from session_start and session_end.

    model: str
    # The model used by all agents. Comes from config.py.

    temperature: float
    # The temperature used by all agents. Comes from config.py.

    current_stage: str
    # Tracks where in the pipeline the session currently is.
    # One of: "planning" | "threat_modelling" | "code_generation" |
    #         "code_review" | "verification" | "complete" | "error"

    error: Optional[str]
    # Populated if any agent or stage fails. Stores the error message.

    # ── Planner ───────────────────────────────────────────────────────────────

    plan: Optional[PlannerOutput]
    # Structured output from the Planner agent.

    plan_decision: Optional[ParticipantDecision]
    # The participant's decision after reviewing the plan.

    # ── Threat Modeller ───────────────────────────────────────────────────────

    rag_context: Optional[list[dict]]
    # The top-3 CWE chunks returned by the RAG retriever.
    # Stored in state for transparency and logging.

    threats: Optional[list[ThreatEntry]]
    # Structured list of threats identified by the Threat Modeller.

    threats_decision: Optional[ParticipantDecision]
    # The participant's decision after reviewing the threat model.

    step_hint_caps: Optional[list[StepHintCap]]
    # Per-step hint depth caps computed by the step classifier after the threat
    # model is approved. Tells the frontend the maximum hint level each plan step
    # may reveal. None until the first /step-caps call.

    # ── Code Generator (HITL redesign) ───────────────────────────────
    # The Code Generator is now a mentor, not a code producer. The participant
    # writes the code themselves using the hint ladder for guidance. These fields
    # record what the participant produced and how much help they needed.

    generated_code: Optional[str]
    # The participant's final code. In the new HITL design this is the human's
    # own code (possibly informed by hints), NOT AI-generated output. Named
    # "generated_code" for schema compatibility with the baseline log.

    code_explanation: Optional[str]
    # Kept for schema compatibility. Not populated in the new HITL design.

    code_decision: Optional[ParticipantDecision]
    # Kept for schema compatibility. Not used in the new HITL design -- code
    # submission is the implicit decision.

    hitl_coding: Optional[HitlCodingMetrics]
    # All HITL metrics for the coding stage: hint levels used, time spent,
    # confidence rating, and annotation gate answers.

    pre_review_prediction: Optional[list[str]]
    # The vulnerabilities the participant predicts the Code Reviewer will find.
    # Collected by the prediction gate before the Code Reviewer runs.
    # Used to measure calibration: did they know what was wrong?

    prediction_accuracy: Optional[float]
    # Fraction of predicted vulnerabilities confirmed by the Code Reviewer.
    # Computed after the Code Reviewer runs. Range 0.0-1.0.
    # ── Code Reviewer ─────────────────────────────────────────────────────────

    bandit_findings_review: Optional[list[dict]]
    # Raw Bandit static analysis findings from the Code Reviewer's MCP call.
    # Stored separately from the Verifier's Bandit run to ensure independence.

    review_findings: Optional[list[ReviewFinding]]
    # The Code Reviewer's structured security findings combining Bandit
    # results with LLM analysis.

    review_decision: Optional[ParticipantDecision]
    # The participant's decision after reviewing the code review findings.

    # ── Verifier ──────────────────────────────────────────────────────────────

    bandit_findings_verify: Optional[list[dict]]
    # Independent Bandit run by the Verifier. Must not reuse
    # bandit_findings_review — the Verifier is a genuine second check.

    verification_result: Optional[VerificationResult]
    # The Verifier's complete output including per-threat verdicts,
    # Bandit findings, and sandbox execution result.

    final_code: Optional[str]
    # The code that passed verification. This is what goes into the log
    # as the "response" field to match the baseline log schema.

    # ── Log record ────────────────────────────────────────────────────────────

    log_entry: Optional[dict]
    # The complete JSONL log record. Populated at the end of the session.


# =============================================================================
# Helper functions
# =============================================================================

def create_initial_state(
    participant_id: str,
    task: str,
    task_id: Optional[str] = None,
    task_order: Optional[int] = None,
) -> AgentState:
    """
    Creates a fresh AgentState at the start of a new session.

    Sets all session metadata fields. All agent output fields start as None
    because no agent has run yet.

    This is the only place AgentState objects should be created. Never
    construct the dict manually in agent or graph code.
    """
    return AgentState(
        # Session metadata
        participant_id=participant_id,
        task=task,
        condition="multiagent",
        task_id=task_id,
        task_order=task_order,
        session_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        session_end=None,
        duration_seconds=None,
        model=MODEL,
        temperature=TEMPERATURE,
        current_stage="planning",
        error=None,

        # Planner
        plan=None,
        plan_decision=None,

        # Threat Modeller
        rag_context=None,
        threats=None,
        threats_decision=None,
        step_hint_caps=None,

        # Code Generator (HITL)
        generated_code=None,
        code_explanation=None,
        code_decision=None,
        hitl_coding=None,
        pre_review_prediction=None,
        prediction_accuracy=None,

        # Code Reviewer
        bandit_findings_review=None,
        review_findings=None,
        review_decision=None,

        # Verifier
        bandit_findings_verify=None,
        verification_result=None,
        final_code=None,

        # Log
        log_entry=None,
    )


def to_log_entry(state: AgentState) -> dict:
    """
    Converts the completed state into a JSONL log record.

    The top-level fields (timestamp, condition, participant_id, model,
    temperature, task, response, duration_seconds) match the baseline log
    schema exactly. The multi_agent_detail field contains the full per-agent
    breakdown for deeper analysis.

    This consistent schema is what allows the evaluation scripts to compare
    baseline and multi-agent sessions directly.
    """
    return {
        # ── Fields shared with baseline schema ────────────────────────────────
        "timestamp":        state["session_start"],
        "condition":        "multiagent",
        "participant_id":   state["participant_id"],
        "model":            state["model"],
        "temperature":      state["temperature"],
        "task":             state["task"],
        "task_id":          state.get("task_id"),
        "task_order":       state.get("task_order"),
        "response":         state.get("final_code") or "",
        "duration_seconds": round(state.get("duration_seconds") or 0.0, 3),

        # ── Multi-agent detail ─────────────────────────────────────────────────
        "multi_agent_detail": {
            "plan":                  state.get("plan"),
            "plan_decision":         state.get("plan_decision"),
            "rag_context_ids":       [
                c.get("metadata", {}).get("cwe_id")
                for c in (state.get("rag_context") or [])
            ],
            "threats":               state.get("threats"),
            "threats_decision":      state.get("threats_decision"),
            "generated_code":        state.get("generated_code"),
            "hitl_coding":           state.get("hitl_coding"),
            "pre_review_prediction": state.get("pre_review_prediction"),
            "prediction_accuracy":   state.get("prediction_accuracy"),
            "bandit_findings_review": state.get("bandit_findings_review"),
            "review_findings":       state.get("review_findings"),
            "review_decision":       state.get("review_decision"),
            "bandit_findings_verify": state.get("bandit_findings_verify"),
            "verification_result":   state.get("verification_result"),
        },
    }
