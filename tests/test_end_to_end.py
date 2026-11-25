"""CB-3105 end to end: submit, one worker pass, the checkpoint, the stored trace."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from procure_pay import worker
from procure_pay.graph import thread_id_for
from procure_pay.models import Claim, Purchase, Task
from procure_pay.task_updates import COMPLETED

URL = "/v1/purchases"
BODY = {"summary": "Renew the Solid design licence for 12 seats"}


def test_cb_3105_runs_from_submit_to_checkpoint(
    seeded_client: TestClient,
    session: Session,
    session_factory: sessionmaker[Session],
    graph: worker.StubGraph,
) -> None:
    reply = seeded_client.post(
        URL, json=BODY, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    assert reply.status_code == 202
    data = reply.json()
    assert (data["purchase_number"], data["task_id"]) == ("CB-3105", "CB-3105-T01")

    assert worker.work_once(session_factory, graph, "worker-e2e") is True

    session.expire_all()
    task = session.scalars(select(Task)).one()
    assert (task.task_id, task.status, task.version) == ("CB-3105-T01", COMPLETED, 3)
    assert session.get(Claim, (task.tenant_id, task.task_id)) is None
    threads = session.scalars(
        text("SELECT DISTINCT thread_id FROM tasks.checkpoints")
    ).all()
    assert threads == [thread_id_for(task.tenant_id, task.task_id)]
    purchase = session.scalars(select(Purchase)).one()
    assert (purchase.purchase_number, purchase.stage, purchase.status) == (
        "CB-3105",
        "ST1",
        "in_progress",
    )

    assert data["request_id"] == f"req-{task.trace_id[:16]}"
