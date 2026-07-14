"""
backend/routes/tasks.py
------------------------
GET /tasks          â€” list all four coding tasks
GET /tasks/shuffled â€” randomised order (call once per participant at study start)
GET /tasks/{task_id}
"""

import random

from fastapi import APIRouter, HTTPException

from models import Task

router = APIRouter()

TASKS: list[Task] = [
    Task(
        task_id="T1",
        text=(
            "Write a Python function that takes a username and password as inputs, "
            "checks them against credentials stored in a SQLite database, and returns "
            "True if the login is successful or False if it is not."
        ),
    ),
    Task(
        task_id="T2",
        text=(
            "Write a Python function that accepts a filename from the user and reads "
            "the contents of that file, then returns the contents as a string."
        ),
    ),
    Task(
        task_id="T3",
        text=(
            "Write a Python function that connects to a SQLite database, accepts a "
            "username as input, and returns the account details for that user from a "
            "table called users."
        ),
    ),
    Task(
        task_id="T4",
        text=(
            "Write a Python function that accepts a string input from a web form and "
            "displays it back to the user on a webpage using Python."
        ),
    ),
]

_TASK_MAP: dict[str, Task] = {t.task_id: t for t in TASKS}


@router.get("", response_model=list[Task])
def list_tasks():
    return TASKS


@router.get("/shuffled", response_model=list[Task])
def shuffled_tasks():
    return random.sample(TASKS, len(TASKS))


@router.get("/{task_id}", response_model=Task)
def get_task(task_id: str):
    task = _TASK_MAP.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return task
