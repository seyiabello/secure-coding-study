"""
baseline/agent.py
-----------------
Single-agent baseline: control condition for the secure coding study.

The participant submits a coding task. GPT-4o returns code directly.
No orchestration, no specialised roles, no security-aware prompting.

This is intentionally minimal. Any added capability here biases the
comparison against the multi-agent system.
"""

import os
import json
import datetime
from pathlib import Path
from openai import OpenAI

from langfuse import observe, propagate_attributes

from config import client, MODEL, TEMPERATURE
from baseline.prompts import SYSTEM_PROMPT

LOG_FILE = str(Path(__file__).parent.parent / "logs" / "baseline_sessions.jsonl")

# ── Core agent function ───────────────────────────────────────────────────────

@observe(name="baseline")
def run_baseline(
    task: str,
    client: OpenAI = client,
    participant_id: str = "unknown",
    task_id: str = "unknown",
) -> str:
    """
    Submit a task to GPT-4o and return the response.

    One system message, one user message, one response.
    No intermediate steps, no review, no iteration.
    """
    session_id = f"{participant_id}_{task_id}"
    with propagate_attributes(
        session_id=session_id,
        user_id=participant_id,
        tags=["baseline"],
    ):
        response = client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task},
            ],
            name="baseline",
        )
    return response.choices[0].message.content

# ── Logging ───────────────────────────────────────────────────────────────────

def log_session(
    participant_id: str,
    task: str,
    response: str,
    duration_seconds: float,
    task_id: str | None = None,
    task_order: int | None = None,
    participant_notes: str | None = None,
) -> None:
    """Append one session record to the JSONL log file."""
    os.makedirs("logs", exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "condition": "baseline",
        "participant_id": participant_id,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "task": task,
        "task_id": task_id,
        "task_order": task_order,
        "response": response,
        "duration_seconds": round(duration_seconds, 3),
        "participant_notes": participant_notes or None,
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

# ── CLI interface (development/testing only) ──────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Baseline agent: control condition")
    print(f"Model: {MODEL}  |  Temperature: {TEMPERATURE}")
    print("Type 'quit' to exit.")
    print("=" * 60)

    participant_id = input("Participant ID (e.g. P01): ").strip() or "DEV"

    while True:
        print()
        task = input("Task: ").strip()

        if task.lower() in ("quit", "exit", "q"):
            print("Session ended.")
            break

        if not task:
            continue

        print("\nGenerating...\n")
        start = datetime.datetime.now(datetime.timezone.utc)

        try:
            response = run_baseline(task)
        except Exception as e:
            print(f"API error: {e}")
            continue

        duration = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()

        print("-" * 60)
        print(response)
        print("-" * 60)
        print(f"Completed in {duration:.1f}s")

        log_session(participant_id, task, response, duration)


if __name__ == "__main__":
    main()
