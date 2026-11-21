"""Tests for taking, renewing and finishing a claim."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from procure_pay import db
from procure_pay.claims import (
    ClaimLostError,
    finish_task,
    renew_claim,
    take_next_task,
    worker_identity,
)
from procure_pay.models import Claim, Task
from procure_pay.task_updates import COMPLETED, RUNNING

KEY = ("t-kabtest001", "CB-3105-T01")


@pytest.fixture
def other_session(migrated_database: str) -> Iterator[Session]:
    engine = db.create_app_engine(db.load_settings())
    try:
        with db.create_session_factory(engine)() as second:
            yield second
    finally:
        engine.dispose()


def test_take_claims_the_oldest_queued_task(
    session: Session, queued_task: Task
) -> None:
    task = take_next_task(session, "worker-a")
    assert task is not None
    assert (task.task_id, task.status, task.version) == ("CB-3105-T01", RUNNING, 2)
    claim = session.get(Claim, KEY)
    assert claim is not None
    assert claim.worker_id == "worker-a"
    assert claim.expires_at - claim.claimed_at == timedelta(seconds=60)


def test_a_locked_task_is_skipped(
    session: Session, other_session: Session, queued_task: Task
) -> None:
    other_session.execute(select(Task).with_for_update())
    assert take_next_task(session, "worker-a") is None
    other_session.rollback()


def test_a_taken_task_is_not_taken_again(
    session: Session, other_session: Session, queued_task: Task
) -> None:
    assert take_next_task(session, "worker-a") is not None
    assert take_next_task(other_session, "worker-b") is None
    claims = session.scalar(select(func.count()).select_from(Claim))
    assert claims == 1


def test_renew_moves_the_expiry(session: Session, queued_task: Task) -> None:
    take_next_task(session, "worker-a")
    claim = session.get(Claim, KEY)
    assert claim is not None
    before = claim.expires_at
    renew_claim(session, *KEY, "worker-a")
    session.refresh(claim)
    assert claim.expires_at > before


def test_another_worker_cannot_renew(session: Session, queued_task: Task) -> None:
    take_next_task(session, "worker-a")
    with pytest.raises(ClaimLostError):
        renew_claim(session, *KEY, "worker-b")


def test_a_claim_that_ran_out_cannot_be_renewed(
    session: Session, queued_task: Task
) -> None:
    take_next_task(session, "worker-a")
    session.execute(
        text("UPDATE tasks.claims SET expires_at = now() - interval '1 second'")
    )
    session.commit()
    with pytest.raises(ClaimLostError):
        renew_claim(session, *KEY, "worker-a")


def test_finish_completes_and_releases(session: Session, queued_task: Task) -> None:
    task = take_next_task(session, "worker-a")
    assert task is not None
    finish_task(session, task, "worker-a")
    assert (task.status, task.version) == (COMPLETED, 3)
    assert session.get(Claim, KEY) is None


def test_finish_without_the_claim_changes_nothing(
    session: Session, queued_task: Task
) -> None:
    take_next_task(session, "worker-a")
    with pytest.raises(ClaimLostError):
        finish_task(session, queued_task, "worker-b")
    session.refresh(queued_task)
    assert queued_task.status == RUNNING
    assert session.get(Claim, KEY) is not None


def test_worker_identity_names_host_and_process() -> None:
    host, _, pid = worker_identity().rpartition(":")
    assert host
    assert pid.isdigit()
