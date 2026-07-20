"""
interface/app.py
-----------------
Streamlit entry point for the secure coding study.

Handles session setup, task-order randomisation, and routing to
baseline_ui or multiagent_ui for the active task.

Run:
    streamlit run interface/app.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path regardless of how Streamlit resolves it.
sys.path.insert(0, str(Path(__file__).parent.parent))

import random

import streamlit as st

TASKS = [
    {
        "task_id": "T1",
        "text": (
            "Write a Python function that takes a username and password as inputs, "
            "checks them against credentials stored in a SQLite database, and returns "
            "True if the login is successful or False if it is not."
        ),
    },
    {
        "task_id": "T2",
        "text": (
            "Write a Python function that accepts a filename from the user and reads "
            "the contents of that file, then returns the contents as a string."
        ),
    },
    {
        "task_id": "T3",
        "text": (
            "Write a Python function that connects to a SQLite database, accepts a "
            "username as input, and returns the account details for that user from a "
            "table called users."
        ),
    },
    {
        "task_id": "T4",
        "text": (
            "Write a Python function that accepts a string input from a web form and "
            "displays it back to the user on a webpage using Python."
        ),
    },
]


# -- Session initialisation ----------------------------------------------------

def _init_session(participant_id: str, condition: str) -> None:
    shuffled = random.sample(TASKS, len(TASKS))
    st.session_state.session_started    = True
    st.session_state.participant_id     = participant_id
    st.session_state.condition          = condition
    st.session_state.task_sequence      = [
        {**t, "task_order": i + 1} for i, t in enumerate(shuffled)
    ]
    st.session_state.current_task_index = 0
    st.session_state.task_complete      = False


# -- Page renderers ------------------------------------------------------------

def _show_setup() -> None:
    st.title("Secure Coding Study")
    st.caption("University of Exeter · COMM514")
    st.markdown("---")

    with st.form("setup_form"):
        participant_id = st.text_input("Participant ID", placeholder="e.g. P01")
        condition = st.radio(
            "Condition",
            options=["baseline", "multiagent"],
            format_func=lambda x: (
                "Baseline" if x == "baseline" else "Multi-Agent Pipeline"
            ),
        )
        submitted = st.form_submit_button("Start Session")

    if submitted:
        if not participant_id.strip():
            st.error("Enter a participant ID before starting.")
            return
        _init_session(participant_id.strip().upper(), condition)
        st.rerun()


def _show_task_header() -> None:
    idx   = st.session_state.current_task_index
    total = len(st.session_state.task_sequence)
    task  = st.session_state.task_sequence[idx]

    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Participant:** {st.session_state.participant_id}")
    col2.markdown(f"**Task {idx + 1} of {total}**")
    col3.markdown(f"**Condition:** {st.session_state.condition}")

    st.progress(idx / total)
    st.markdown("---")
    st.subheader("Task")
    st.info(task["text"])
    st.markdown("---")


def _advance_task() -> None:
    st.session_state.current_task_index += 1
    st.session_state.task_complete = False
    for key in ["pipeline_config", "pipeline_stage"]:
        st.session_state.pop(key, None)


def _show_between_tasks() -> None:
    idx   = st.session_state.current_task_index
    total = len(st.session_state.task_sequence)
    st.success(f"Task {idx} of {total} complete.")
    if st.button("Continue to next task →"):
        _advance_task()
        st.rerun()


def _show_session_complete() -> None:
    st.balloons()
    st.title("All tasks complete")
    st.success(
        f"Thank you, {st.session_state.participant_id}. "
        "The session has been logged. You can close this window."
    )


# -- Main ----------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Secure Coding Study",
        page_icon="🔒",
        layout="wide",
    )

    if not st.session_state.get("session_started"):
        _show_setup()
        return

    idx   = st.session_state.current_task_index
    total = len(st.session_state.task_sequence)

    if idx >= total:
        _show_session_complete()
        return

    if st.session_state.get("task_complete"):
        _show_between_tasks()
        return

    _show_task_header()

    task      = st.session_state.task_sequence[idx]
    condition = st.session_state.condition

    if condition == "baseline":
        from interface.baseline_ui import show_task
    else:
        from interface.multiagent_ui import show_task

    show_task(
        participant_id=st.session_state.participant_id,
        task=task["text"],
        task_id=task["task_id"],
        task_order=task["task_order"],
    )


if __name__ == "__main__":
    main()