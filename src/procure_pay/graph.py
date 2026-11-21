"""The stub LangGraph graph that M1 runs for a task (L3, the orchestrator).

One node, saved by LangGraph's PostgreSQL saver with sync durability: each
checkpoint is written before the graph carries on (AD-061).
"""

from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class StubState(TypedDict):
    """What the stub graph keeps for a task: plain data only (strict msgpack)."""

    task_id: str
    steps_done: int


def stub_step(state: StubState) -> dict[str, int]:
    """Do the one stub step: count it."""
    return {"steps_done": state["steps_done"] + 1}


def thread_id_for(tenant_id: str, task_id: str) -> str:
    """Join the tenant ID and the task ID with a colon (Appendix F, point 2)."""
    return f"{tenant_id}:{task_id}"


def build_graph(
    saver: PostgresSaver,
) -> CompiledStateGraph[StubState, None, StubState, StubState]:
    """Build the one-node stub graph, saved by the given checkpoint saver."""
    builder = StateGraph(StubState)
    builder.add_node("stub_step", stub_step)
    builder.add_edge(START, "stub_step")
    builder.add_edge("stub_step", END)
    return builder.compile(checkpointer=saver)


def run_task(
    graph: CompiledStateGraph[StubState, None, StubState, StubState],
    tenant_id: str,
    task_id: str,
) -> None:
    """Run the graph for one task; it returns only once the run has finished."""
    graph.invoke(
        {"task_id": task_id, "steps_done": 0},
        {"configurable": {"thread_id": thread_id_for(tenant_id, task_id)}},
        durability="sync",
    )
