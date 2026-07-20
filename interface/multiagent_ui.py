"""
interface/multiagent_ui.py
---------------------------
Multi-agent condition UI.

The participant reviews and approves each agent's output before the next agent
runs. Human decisions are recorded as ParticipantDecision at every stage.

Pipeline stages (current_stage values set by each agent):
    planning         -- pipeline not yet started
    threat_modelling -- Planner done, awaiting plan_decision
    code_generation  -- Threat Modeller done, awaiting threats_decision
    code_review      -- Code Generator done, awaiting code_decision
    verification     -- Code Reviewer done, awaiting review_decision
    complete         -- Verifier + Finalise done, session logged

show_task() is the only public function. app.py calls it after rendering the
task header. Task complete is signalled by setting st.session_state.task_complete.
"""

import asyncio
import datetime
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from multiagent.graph import get_current_state, resume_session, start_session
from multiagent.state import ParticipantDecision


# -- Async helper --------------------------------------------------------------
# ThreadPoolExecutor gives each call a clean thread with its own event loop,
# avoiding "event loop already running" errors in some Streamlit environments.

def _run(coro):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _regenerate_fixed_code(code: str, findings: list) -> str:
    """Ask GPT-4o to rewrite the code addressing the review findings."""
    from config import MODEL, TEMPERATURE, client

    if not findings:
        return code

    issues = "\n".join(
        f"- {f['cwe_id']} [{f['severity']}]: {f['description']}\n  Fix: {f['suggested_fix']}"
        for f in findings
    )
    prompt = (
        f"The following Python code has security vulnerabilities identified by a code review.\n\n"
        f"CURRENT CODE:\n```python\n{code}\n```\n\n"
        f"SECURITY ISSUES TO FIX:\n{issues}\n\n"
        f"Rewrite the code to fix all identified security issues. "
        f"Keep the same function signature and purpose. "
        f"Return only the corrected Python code with no explanation or markdown."
    )
    response = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.splitlines()[:-1])
    return raw.strip()


async def _rerun_code_reviewer(new_code: str, state: dict) -> dict:
    """Re-run the Code Reviewer agent directly on new code."""
    from multiagent.agents.code_reviewer import run_code_reviewer
    temp_state = {**state, "generated_code": new_code}
    return await run_code_reviewer(temp_state)


def _decision(action: str, revised_content: str | None = None) -> ParticipantDecision:
    return {
        "action": action,
        "revised_content": revised_content or None,
        "timestamp": _now(),
    }


# -- Stage renderers -----------------------------------------------------------

def _show_plan(state: dict, config: dict, idx: int) -> None:
    plan = state.get("plan") or {}

    st.subheader("Stage 1 of 5 — Plan")
    st.caption(
        "Review the plan below. Edit the security requirements if you think anything is missing "
        "or incorrect — they will inform the Threat Modeller."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Implementation steps**")
        for i, step in enumerate(plan.get("steps", []), 1):
            st.markdown(f"{i}. {step}")
        st.markdown("---")
        st.markdown(f"**Scope**\n\n{plan.get('scope', '')}")

    with col2:
        st.markdown("**Security requirements (editable — one per line)**")
        default_reqs = "\n".join(plan.get("security_requirements", []))
        edited_reqs = st.text_area(
            "Security requirements",
            value=default_reqs,
            height=200,
            key=f"plan_reqs_{idx}",
            label_visibility="collapsed",
        )

    st.markdown("---")
    notes = st.text_area(
        "Notes (optional)",
        key=f"plan_notes_{idx}",
        height=80,
    )

    if st.button("Approve and continue →", key=f"plan_approve_{idx}", type="primary"):
        original_reqs = plan.get("security_requirements", [])
        new_reqs      = [r.strip() for r in edited_reqs.splitlines() if r.strip()]
        reqs_changed  = new_reqs != original_reqs

        action = "override" if reqs_changed else ("revise" if notes.strip() else "approve")
        decision = _decision(action, notes.strip() or None)

        state_update = {"plan_decision": decision}
        if reqs_changed:
            state_update["plan"] = {**plan, "security_requirements": new_reqs}

        with st.spinner("Running Threat Modeller..."):
            _run(resume_session(config, state_update))
        st.rerun()


def _show_threats(state: dict, config: dict, idx: int) -> None:
    threats = state.get("threats") or []

    st.subheader("Stage 2 of 5 — Threat Model")
    st.caption("These are the security threats identified for this task. Review each one, then approve to continue.")

    severity_icon = {"Critical": "🔴", "High": "🟠", "Medium": "🟡"}

    for t in threats:
        icon = severity_icon.get(t.get("severity", ""), "⚪")
        with st.expander(
            f"{icon} {t['cwe_id']} — {t['name']} [{t['severity']}]",
            expanded=True,
        ):
            st.markdown(f"**Description:** {t['description']}")
            st.markdown(f"**Required mitigation:** {t['mitigation']}")

    st.markdown("---")
    notes = st.text_area(
        "Notes (optional)",
        key=f"threats_notes_{idx}",
        height=80,
    )

    if st.button("Approve and continue →", key=f"threats_approve_{idx}", type="primary"):
        action   = "revise" if notes.strip() else "approve"
        decision = _decision(action, notes.strip() or None)
        with st.spinner("Running Code Generator..."):
            _run(resume_session(config, {"threats_decision": decision}))
        st.rerun()


def _show_code(state: dict, config: dict, idx: int) -> None:
    code        = state.get("generated_code") or ""
    explanation = state.get("code_explanation") or ""

    st.subheader("Stage 3 of 5 — Generated Code")
    st.caption("Review the code. You can edit it directly before continuing.")

    if explanation:
        st.info(explanation)

    edited = st.text_area(
        "Code (editable)",
        value=code,
        height=420,
        key=f"code_edit_{idx}",
    )

    notes = st.text_area(
        "Notes (optional)",
        key=f"code_notes_{idx}",
        height=80,
    )

    if st.button("Approve and continue →", key=f"code_approve_{idx}", type="primary"):
        code_changed = edited.strip() != code.strip()
        if code_changed:
            action = "override"
        elif notes.strip():
            action = "revise"
        else:
            action = "approve"

        decision     = _decision(action, notes.strip() or None)
        state_update = {"code_decision": decision}

        if code_changed:
            state_update["generated_code"] = edited.strip()

        with st.spinner("Running Code Reviewer..."):
            _run(resume_session(config, state_update))
        st.rerun()


def _show_review(state: dict, config: dict, idx: int) -> None:
    # Session-state keys scoped to this task index
    findings_key = f"rereview_findings_{idx}"
    bandit_key   = f"rereview_bandit_{idx}"
    code_key     = f"review_code_edit_{idx}"

    # Use re-reviewed data if a re-generation cycle has run, else original
    is_rereviewed = findings_key in st.session_state
    findings = st.session_state.get(findings_key, state.get("review_findings") or [])
    bandit   = st.session_state.get(bandit_key,   state.get("bandit_findings_review") or [])
    code     = state.get("generated_code") or ""

    # Initialise the code editor with the original code on first render
    if code_key not in st.session_state:
        st.session_state[code_key] = code

    st.subheader("Stage 4 of 5 — Code Review")

    if is_rereviewed:
        st.info(
            "Showing updated findings after re-generation. "
            "Edit the code further if needed, then approve to run the Verifier."
        )
    else:
        st.caption(
            "Review the security findings on the left. Fix the code on the right "
            "— manually or via re-generate — then approve to run the Verifier."
        )

    severity_icon = {"Critical": "🔴", "High": "🟠", "Medium": "🟡"}
    left, right = st.columns([1, 1])

    with left:
        st.markdown("**Security findings**")
        if not findings:
            st.success("No issues found." if is_rereviewed else "No security issues found.")
        else:
            for f in findings:
                icon       = severity_icon.get(f.get("severity", ""), "⚪")
                source_tag = "Bandit" if f.get("source") == "bandit" else "LLM review"
                with st.expander(
                    f"{icon} {f['cwe_id']} [{f['severity']}] — {source_tag}",
                    expanded=True,
                ):
                    st.markdown(f"**Issue:** {f['description']}")
                    st.markdown(f"**Suggested fix:** {f['suggested_fix']}")
                    if f.get("line_number"):
                        st.caption(f"Line {f['line_number']}")

        if bandit:
            with st.expander(f"Bandit — {len(bandit)} finding(s)"):
                for b in bandit:
                    st.markdown(
                        f"- Line {b.get('line_number', '?')}: `{b.get('test_id', '')}` "
                        f"— {b.get('description', '')} [{b.get('severity', '?')}]"
                    )

        st.markdown("---")
        if st.button(
            "Re-generate and re-review",
            key=f"regen_review_btn_{idx}",
            help="Ask the Code Generator to fix the issues, then re-run the Code Reviewer so you can see updated findings.",
        ):
            current_code = st.session_state.get(code_key, code)
            with st.spinner("Re-generating code to fix issues..."):
                new_code = _regenerate_fixed_code(current_code, findings)
            with st.spinner("Re-running Code Reviewer on new code..."):
                result = _run(_rerun_code_reviewer(new_code, state))

            # Push new code into the editor and store updated findings
            st.session_state[code_key]     = new_code
            st.session_state[findings_key] = result.get("review_findings") or []
            st.session_state[bandit_key]   = result.get("bandit_findings_review") or []
            st.rerun()

    with right:
        st.markdown("**Code (editable)**")
        st.text_area(
            "Edit code",
            key=code_key,
            height=420,
            label_visibility="collapsed",
        )

    st.markdown("---")
    notes = st.text_area(
        "Notes (optional)",
        key=f"review_notes_{idx}",
        height=80,
    )

    if st.button("Approve and continue →", key=f"review_approve_{idx}", type="primary"):
        final_code   = st.session_state.get(code_key, code)
        code_changed = final_code.strip() != code.strip()

        if code_changed:
            action = "override"
        elif notes.strip():
            action = "revise"
        else:
            action = "approve"

        decision     = _decision(action, notes.strip() or None)
        state_update = {"review_decision": decision}

        if code_changed:
            state_update["generated_code"] = final_code.strip()

        # If re-review ran, log the updated findings too
        if is_rereviewed:
            state_update["review_findings"]       = findings
            state_update["bandit_findings_review"] = bandit

        with st.spinner("Running Verifier — this may take a moment..."):
            _run(resume_session(config, state_update))
        st.rerun()


def _show_complete(state: dict) -> None:
    vr = state.get("verification_result") or {}

    st.subheader("Stage 5 of 5 — Verification")

    overall = vr.get("overall_pass", False)
    if overall:
        st.success("Overall verdict: PASS — all mitigations implemented and code runs correctly.")
    else:
        st.error(
            "Overall verdict: FAIL — one or more mitigations were not fully implemented. "
            "See the threat verdicts below."
        )

    if vr.get("notes"):
        st.markdown(f"*{vr['notes']}*")

    threats_checked = vr.get("threats_checked") or []
    if threats_checked:
        st.markdown("**Per-threat verdicts:**")
        for t in threats_checked:
            icon = "✅" if t["passed"] else "❌"
            st.markdown(f"{icon} **{t['cwe_id']}** — {t['notes']}")

    exec_result = vr.get("execution_result") or {}
    with st.expander("Sandbox execution"):
        passed    = exec_result.get("passed", False)
        exit_code = exec_result.get("exit_code", "?")
        st.markdown(f"**Passed:** {'Yes' if passed else 'No'}  |  **Exit code:** {exit_code}")
        if exec_result.get("stdout"):
            st.code(exec_result["stdout"][:500], language="text")
        if exec_result.get("stderr"):
            st.code(exec_result["stderr"][:500], language="text")

    final_code = state.get("final_code") or ""
    if final_code:
        st.markdown("**Final code:**")
        st.code(final_code, language="python")

    st.caption(f"Session logged · Duration: {state.get('duration_seconds', 0):.1f}s")
    st.markdown("---")

    if st.button("Mark task complete →", type="primary"):
        st.session_state.task_complete = True
        st.rerun()


# -- Public entry point --------------------------------------------------------

def show_task(
    participant_id: str,
    task: str,
    task_id: str,
    task_order: int,
) -> None:
    idx        = st.session_state.current_task_index
    config_key = f"pipeline_config_{idx}"

    # -- Start pipeline --------------------------------------------------------
    if config_key not in st.session_state:
        st.markdown(
            "The pipeline will run five agents in sequence. "
            "You will review and approve each stage before the next agent runs."
        )
        if st.button("Start pipeline →", key=f"start_{idx}", type="primary"):
            with st.spinner("Running Planner..."):
                config = _run(
                    start_session(participant_id, task, task_id, task_order)
                )
            st.session_state[config_key] = config
            st.rerun()
        return

    # -- Route to current stage ------------------------------------------------
    config = st.session_state[config_key]
    state  = get_current_state(config)
    stage  = state.get("current_stage", "planning")

    if stage == "error":
        st.error(f"Pipeline error: {state.get('error')}")
        return

    stage_map = {
        "threat_modelling": _show_plan,
        "code_generation":  _show_threats,
        "code_review":      _show_code,
        "verification":     _show_review,
    }

    if stage in stage_map:
        stage_map[stage](state, config, idx)
    elif stage == "complete":
        _show_complete(state)
    else:
        st.info(f"Pipeline running... (stage: {stage})")