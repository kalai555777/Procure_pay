"""The one place a task's status changes (L4, task state).

Every change is checked against the allowed moves, and against the task's
version: SQLAlchemy adds AND version = <old> to the UPDATE (version_id_col)
and raises StaleDataError if no row matched.
"""

from sqlalchemy.orm import Session

from procure_pay.models import Task

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"

ALLOWED_MOVES = frozenset({(QUEUED, RUNNING), (RUNNING, COMPLETED)})


class MoveNotAllowedError(Exception):
    """A status change that is not on the list of allowed moves."""


def move_task(session: Session, task: Task, new_status: str) -> None:
    """Change a task's status if the move is allowed; the caller commits.

    Raises:
        MoveNotAllowedError: the move is not on the list.
        StaleDataError: someone changed the task since it was read.
    """
    move = (task.status, new_status)
    if move not in ALLOWED_MOVES:
        raise MoveNotAllowedError(f"{task.status} to {new_status} is not allowed")
    task.status = new_status
    session.flush()
