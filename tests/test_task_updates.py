"""Tests for the one place a task's status changes."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from procure_pay.models import Task
from procure_pay.task_updates import (
    COMPLETED,
    QUEUED,
    RUNNING,
    MoveNotAllowedError,
    move_task,
)


def test_queued_to_running_raises_the_version(
    session: Session, queued_task: Task
) -> None:
    move_task(session, queued_task, RUNNING)
    session.commit()
    assert (queued_task.status, queued_task.version) == (RUNNING, 2)


def test_running_to_completed_raises_it_again(
    session: Session, queued_task: Task
) -> None:
    move_task(session, queued_task, RUNNING)
    move_task(session, queued_task, COMPLETED)
    session.commit()
    assert (queued_task.status, queued_task.version) == (COMPLETED, 3)


def test_a_move_not_on_the_list_is_refused(session: Session, queued_task: Task) -> None:
    with pytest.raises(MoveNotAllowedError):
        move_task(session, queued_task, COMPLETED)
    assert queued_task.status == QUEUED


def test_a_stale_version_is_refused(session: Session, queued_task: Task) -> None:
    session.execute(
        text("UPDATE tasks.tasks SET version = 5 WHERE task_id = :task_id"),
        {"task_id": queued_task.task_id},
    )
    with pytest.raises(StaleDataError):
        move_task(session, queued_task, RUNNING)
