"""
interface/baseline_ui.py
-------------------------
Baseline condition UI.

The participant sees the task (already rendered by app.py), clicks Generate,
and receives a single GPT-4o response with no orchestration or security review.

show_task() is the only public function. app.py calls it after rendering the
task header. When the participant marks the task complete, this function sets
st.session_state.task_complete = True and calls st.rerun() so app.py advances.
"""

import datetime

import streamlit as st

from baseline.agent import log_session, run_baseline


def show_task(
    participant_id: str,
    task: str,
    task_id: str,
    task_order: int,
) -> None:
    # Key scoped to task index so state never bleeds between tasks.
    idx          = st.session_state.current_task_index
    response_key = f"bl_response_{idx}"
    duration_key = f"bl_duration_{idx}"
    logged_key   = f"bl_logged_{idx}"

    already_generated = response_key in st.session_state

    # -- Generate code ---------------------------------------------------------

    if not already_generated:
        if st.button("Generate Code", type="primary"):
            with st.spinner("Generating..."):
                start = datetime.datetime.now(datetime.timezone.utc)
                try:
                    response = run_baseline(task)
                except Exception as e:
                    st.error(f"API error: {e}")
                    return
                duration = (
                    datetime.datetime.now(datetime.timezone.utc) - start
                ).total_seconds()

            st.session_state[response_key] = response
            st.session_state[duration_key] = duration
            st.rerun()
        return

    # -- Show result -----------------------------------------------------------

    response = st.session_state[response_key]
    duration = st.session_state[duration_key]

    st.subheader("Generated Code")
    st.code(response, language="python")
    st.caption(f"Generated in {duration:.1f}s")

    st.markdown("---")

    # -- Participant notes -----------------------------------------------------

    notes = st.text_area(
        "Your assessment (optional) — does this code look secure to you? "
        "Note any concerns before marking complete.",
        key=f"bl_notes_{idx}",
        height=100,
    )

    # -- Complete task ---------------------------------------------------------

    if st.button("Mark task complete →", type="primary"):
        # Log on completion so participant notes are captured.
        if not st.session_state.get(logged_key):
            log_session(
                participant_id=participant_id,
                task=task,
                response=response,
                duration_seconds=duration,
                task_id=task_id,
                task_order=task_order,
                participant_notes=notes.strip() or None,
            )
            st.session_state[logged_key] = True
        st.session_state.task_complete = True
        st.rerun()