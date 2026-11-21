"""Tests for the stub graph: its checkpoint, thread ID and strict reading."""

from collections.abc import Iterator

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde import _msgpack
from psycopg import Connection
from psycopg.rows import DictRow
from psycopg_pool import ConnectionPool

from procure_pay import db
from procure_pay.graph import build_graph, run_task, thread_id_for

THREAD = "t-kabtest001:CB-3105-T01"


@pytest.fixture
def checkpoint_pool(
    migrated_database: str,
) -> Iterator[ConnectionPool[Connection[DictRow]]]:
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        yield pool
    finally:
        pool.close()


def test_the_thread_id_joins_tenant_and_task() -> None:
    assert thread_id_for("t-jri9l63xto", "CB-3105-T01") == "t-jri9l63xto:CB-3105-T01"


def test_the_checkpoint_is_saved_under_the_joined_thread_id(
    checkpoint_pool: ConnectionPool[Connection[DictRow]],
) -> None:
    graph = build_graph(PostgresSaver(checkpoint_pool))
    run_task(graph, "t-kabtest001", "CB-3105-T01")
    with checkpoint_pool.connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM tasks.checkpoints"
        ).fetchall()
    assert [row["thread_id"] for row in rows] == [THREAD]
    state = graph.get_state({"configurable": {"thread_id": THREAD}})
    assert state.values == {"task_id": "CB-3105-T01", "steps_done": 1}


def test_strict_msgpack_is_on() -> None:
    assert _msgpack.STRICT_MSGPACK_ENABLED is True
