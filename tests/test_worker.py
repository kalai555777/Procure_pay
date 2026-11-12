"""Tests for the worker stub."""

import signal
import threading
from collections.abc import Iterator

import pytest

from procure_pay import worker


@pytest.fixture
def restore_signal_handlers() -> Iterator[None]:
    """Put pytest's own signal handlers back after the test."""
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_run_returns_at_once_when_stop_is_already_set() -> None:
    stop = threading.Event()
    stop.set()
    assert worker.run(stop, poll_seconds=0.01) == 0


def test_run_keeps_waiting_until_stop_is_set() -> None:
    stop = threading.Event()
    threading.Timer(0.05, stop.set).start()
    assert worker.run(stop, poll_seconds=0.01) >= 1


@pytest.mark.usefixtures("restore_signal_handlers")
def test_main_stops_cleanly_on_sigterm() -> None:
    threading.Timer(0.2, signal.raise_signal, args=(signal.SIGTERM,)).start()
    worker.main()  # returns only if SIGTERM was handled
