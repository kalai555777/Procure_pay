"""Clearbuy's worker: a stub for now.

Later it will claim tasks and run LangGraph steps (M1 Piece 6).
For now it starts, says it is ready, and waits until it is asked
to stop, so Docker and Fargate Spot can stop it cleanly.
"""

import logging
import signal
import threading
from types import FrameType

logger = logging.getLogger("procure_pay.worker")


def run(stop: threading.Event, poll_seconds: float = 1.0) -> int:
    """Wait until `stop` is set; return how many times it checked."""
    logger.info("worker ready")
    loops = 0
    while not stop.wait(poll_seconds):
        loops += 1
    logger.info("worker stopping")
    return loops


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
    run(stop)


if __name__ == "__main__":  # pragma: no cover
    main()
