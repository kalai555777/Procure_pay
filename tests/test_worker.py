"""Tests for the worker: one pass, the renewal thread, the loop and SIGTERM."""

import signal
import threading
import time
from collections.abc import Iterator

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from procure_pay import db, worker
from procure_pay.graph import build_graph
from procure_pay.models import Claim, Task
from procure_pay.task_updates import COMPLETED, RUNNING

KEY = ("t-kabtest001", "CB-3105-T01")


@pytest.fixture
def restore_signal_handlers() -> Iterator[None]:
    """Put pytest's own signal handlers back after the test."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


@pytest.fixture
def session_factory(migrated_database: str) -> Iterator[sessionmaker[Session]]:
    engine = db.create_app_engine(db.load_settings())
    try:
        yield db.create_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture
def graph(migrated_database: str) -> Iterator[worker.StubGraph]:
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        yield build_graph(PostgresSaver(pool))
    finally:
        pool.close()


def test_nothing_queued_means_no_work(
    session_factory: sessionmaker[Session], graph: worker.StubGraph
) -> None:
    assert worker.work_once(session_factory, graph, "worker-a") is False


def test_one_pass_completes_cb_3105(
    session: Session,
    queued_task: Task,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    assert worker.work_once(session_factory, graph, "worker-a") is True
    session.refresh(queued_task)
    assert (queued_task.status, queued_task.version) == (COMPLETED, 3)
    assert session.get(Claim, KEY) is None
    threads = session.scalars(
        text("SELECT DISTINCT thread_id FROM tasks.checkpoints")
    ).all()
    assert threads == ["t-kabtest001:CB-3105-T01"]


def test_the_claim_is_renewed_during_a_long_step(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    queued_task: Task,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    def slow(graph: worker.StubGraph, tenant_id: str, task_id: str) -> None:
        time.sleep(0.2)

    monkeypatch.setattr(worker, "run_task", slow)
    assert worker.work_once(session_factory, graph, "worker-a", renew_seconds=0.05)
    session.refresh(queued_task)
    assert queued_task.status == COMPLETED


def test_a_lost_claim_is_not_finished(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    queued_task: Task,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    def stolen(graph: worker.StubGraph, tenant_id: str, task_id: str) -> None:
        with session_factory() as other:
            other.execute(text("UPDATE tasks.claims SET worker_id = 'worker-b'"))
            other.commit()
        time.sleep(0.2)

    monkeypatch.setattr(worker, "run_task", stolen)
    assert worker.work_once(session_factory, graph, "worker-a", renew_seconds=0.05)
    session.refresh(queued_task)
    assert queued_task.status == RUNNING
    claim = session.get(Claim, KEY)
    assert claim is not None
    assert claim.worker_id == "worker-b"


def test_a_failed_step_is_not_finished(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    queued_task: Task,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    def broken(graph: worker.StubGraph, tenant_id: str, task_id: str) -> None:
        raise RuntimeError("stub step failed")

    monkeypatch.setattr(worker, "run_task", broken)
    assert worker.work_once(session_factory, graph, "worker-a")
    session.refresh(queued_task)
    assert queued_task.status == RUNNING
    assert session.get(Claim, KEY) is not None


def test_a_changed_task_is_not_finished(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    queued_task: Task,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    def changed(graph: worker.StubGraph, tenant_id: str, task_id: str) -> None:
        with session_factory() as other:
            other.execute(text("UPDATE tasks.tasks SET version = 9"))
            other.commit()

    monkeypatch.setattr(worker, "run_task", changed)
    assert worker.work_once(session_factory, graph, "worker-a")
    session.refresh(queued_task)
    assert (queued_task.status, queued_task.version) == (RUNNING, 9)
    assert session.get(Claim, KEY) is not None


def test_run_returns_at_once_when_stop_is_already_set() -> None:
    stop = threading.Event()
    stop.set()
    assert worker.run(stop, lambda: False, poll_seconds=0.01) == 0


def test_run_counts_the_tasks_it_handles() -> None:
    stop = threading.Event()
    results = iter([True, True])
    threading.Timer(0.1, stop.set).start()
    assert worker.run(stop, lambda: next(results, False), poll_seconds=0.01) == 2


@pytest.mark.usefixtures("restore_signal_handlers", "migrated_database")
def test_main_stops_cleanly_on_sigterm() -> None:
    threading.Timer(0.5, signal.raise_signal, args=(signal.SIGTERM,)).start()
    worker.main()
