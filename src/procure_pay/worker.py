"""Clearbuy's worker: claims tasks and runs the stub graph (L3, the orchestrator).

Each pass takes the oldest queued task, keeps its claim renewed in a background
thread, runs the graph, then finishes the task. SIGTERM ends the loop cleanly,
so Docker and Fargate Spot can stop it.
"""

import functools
import logging
import signal
import threading
from collections.abc import Callable
from types import FrameType

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from procure_pay import db
from procure_pay.claims import (
    RENEW_EVERY_SECONDS,
    ClaimLostError,
    finish_task,
    renew_claim,
    take_next_task,
    worker_identity,
)
from procure_pay.graph import StubState, build_graph, run_task

logger = logging.getLogger("procure_pay.worker")

POLL_SECONDS = 2.0

StubGraph = CompiledStateGraph[StubState, None, StubState, StubState]


def _keep_renewing(
    session_factory: sessionmaker[Session],
    tenant_id: str,
    task_id: str,
    worker_id: str,
    every: float,
    done: threading.Event,
    lost: threading.Event,
) -> None:
    """Renew the claim every `every` seconds until `done` is set or it is lost."""
    with session_factory() as session:
        while not done.wait(every):
            try:
                renew_claim(session, tenant_id, task_id, worker_id)
            except ClaimLostError:
                logger.warning("claim lost on %s:%s", tenant_id, task_id)
                lost.set()
                return


def work_once(
    session_factory: sessionmaker[Session],
    graph: StubGraph,
    worker_id: str,
    renew_seconds: float = RENEW_EVERY_SECONDS,
) -> bool:
    """Take, run and finish one task; return False if none was queued."""
    with session_factory() as session:
        task = take_next_task(session, worker_id)
        if task is None:
            return False
        name = f"{task.tenant_id}:{task.task_id}"
        logger.info("claimed %s", name)
        done = threading.Event()
        lost = threading.Event()
        renewer = threading.Thread(
            target=_keep_renewing,
            args=(
                session_factory,
                task.tenant_id,
                task.task_id,
                worker_id,
                renew_seconds,
                done,
                lost,
            ),
            daemon=True,
        )
        renewer.start()
        try:
            run_task(graph, task.tenant_id, task.task_id)
        except Exception:
            logger.exception("the graph failed on %s; not finishing", name)
            return True
        finally:
            done.set()
            renewer.join()
        if lost.is_set():
            logger.warning("not finishing %s: the claim was lost", name)
            return True
        try:
            finish_task(session, task, worker_id)
        except ClaimLostError, StaleDataError:
            logger.warning("could not finish %s; it was changed", name)
            return True
        logger.info("completed %s", name)
        return True


def run(
    stop: threading.Event,
    work: Callable[[], bool],
    poll_seconds: float = POLL_SECONDS,
) -> int:
    """Do work until `stop` is set; return how many tasks were handled."""
    logger.info("worker ready")
    handled = 0
    while not stop.is_set():
        if work():
            handled += 1
        elif stop.wait(poll_seconds):
            break
    logger.info("worker stopping")
    return handled


def main() -> None:
    """Start the worker and stop it cleanly on SIGTERM or SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stop = threading.Event()

    def handle_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    settings = db.load_settings()
    engine = db.create_app_engine(settings)
    pool = db.create_checkpoint_pool(settings)
    pool.open(wait=True, timeout=30)
    try:
        graph = build_graph(PostgresSaver(pool))
        work = functools.partial(
            work_once, db.create_session_factory(engine), graph, worker_identity()
        )
        run(stop, work)
    finally:
        pool.close()
        engine.dispose()


if __name__ == "__main__":  # pragma: no cover
    main()
