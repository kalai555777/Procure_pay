"""A worker's claim on a task: take, renew, finish (L4, task state).

A claim lasts 60 seconds and is renewed every 20 while the worker works
(AD-090). Times come from the database's clock, never the worker's.
"""

import os
import socket
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from procure_pay.models import Claim, Task
from procure_pay.task_updates import COMPLETED, QUEUED, RUNNING, move_task

CLAIM_LENGTH = timedelta(seconds=60)
RENEW_EVERY_SECONDS = 20


class ClaimLostError(Exception):
    """The worker no longer holds the claim on its task, so it must stop."""


def worker_identity() -> str:
    """Name this worker by host name and process ID; M1-13 uses ECS's task ID."""
    return f"{socket.gethostname()}:{os.getpid()}"


def take_next_task(session: Session, worker_id: str) -> Task | None:
    """Claim the oldest queued task and mark it running, in one transaction."""
    query = (
        select(Task)
        .where(Task.status == QUEUED)
        .order_by(Task.created_at, Task.task_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.scalars(query).first()
    if task is None:
        session.rollback()
        return None
    session.add(
        Claim(
            tenant_id=task.tenant_id,
            task_id=task.task_id,
            worker_id=worker_id,
            expires_at=func.now() + CLAIM_LENGTH,
        )
    )
    move_task(session, task, RUNNING)
    session.commit()
    return task


def renew_claim(session: Session, tenant_id: str, task_id: str, worker_id: str) -> None:
    """Push the claim's expiry 60 seconds ahead, if this worker still holds it.

    Raises:
        ClaimLostError: the claim is gone, held by another worker, or ran out.
    """
    statement = (
        update(Claim)
        .where(
            Claim.tenant_id == tenant_id,
            Claim.task_id == task_id,
            Claim.worker_id == worker_id,
            Claim.expires_at > func.now(),
        )
        .values(expires_at=func.now() + CLAIM_LENGTH)
    )
    renewed = session.connection().execute(statement).rowcount
    session.commit()
    if renewed != 1:
        raise ClaimLostError(f"{worker_id} no longer holds {tenant_id}:{task_id}")


def finish_task(session: Session, task: Task, worker_id: str) -> None:
    """Mark the task completed and release the claim, in one transaction.

    Raises:
        ClaimLostError: this worker no longer holds the claim.
        StaleDataError: someone changed the task since it was read.
    """
    try:
        statement = delete(Claim).where(
            Claim.tenant_id == task.tenant_id,
            Claim.task_id == task.task_id,
            Claim.worker_id == worker_id,
        )
        if session.connection().execute(statement).rowcount != 1:
            raise ClaimLostError(
                f"{worker_id} no longer holds {task.tenant_id}:{task.task_id}"
            )
        move_task(session, task, COMPLETED)
        session.commit()
    except Exception:
        session.rollback()
        raise
