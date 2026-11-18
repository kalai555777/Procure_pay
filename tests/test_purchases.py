"""Tests for POST /v1/purchases (CB-3105)."""

import re
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procure_pay import db, seed
from procure_pay.fixed_identity import FIXED_REQUESTER_ID
from procure_pay.main import app
from procure_pay.models import Purchase, PurchaseCounter, Task
from procure_pay.purchases import get_session

BODY = {"summary": "Renew the Solid design licence for 12 seats"}
URL = "/v1/purchases"
REQUEST_ID = re.compile(r"req-[0-9a-f]{16}")


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4())}


@pytest.fixture
def client(migrated_database: str) -> Iterator[TestClient]:
    engine = db.create_app_engine(db.load_settings())
    factory = db.create_session_factory(engine)

    def _test_session() -> Iterator[Session]:
        with factory() as request_session:
            yield request_session

    app.dependency_overrides[get_session] = _test_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def seeded_client(client: TestClient, session: Session) -> TestClient:
    seed.seed(session)
    return client


def test_submit_saves_cb_3105_and_its_task(
    seeded_client: TestClient, session: Session
) -> None:
    reply = seeded_client.post(URL, json=BODY, headers=_headers())
    assert reply.status_code == 202
    data = reply.json()
    assert data["purchase_number"] == "CB-3105"
    assert data["task_id"] == "CB-3105-T01"
    assert REQUEST_ID.fullmatch(data["request_id"])
    session.expire_all()
    purchase = session.scalars(select(Purchase)).one()
    assert purchase.stage == "ST1"
    assert purchase.status == "in_progress"
    assert purchase.requester == FIXED_REQUESTER_ID
    assert purchase.request_details == BODY
    task = session.scalars(select(Task)).one()
    assert task.status == "queued"
    assert task.version == 1
    assert task.purchase_number == "CB-3105"
    assert task.trace_id.startswith(data["request_id"][4:])
    counter = session.get(PurchaseCounter, purchase.tenant_id)
    assert counter is not None
    assert counter.next_number == 3106


def test_the_next_submit_gets_cb_3106(seeded_client: TestClient) -> None:
    seeded_client.post(URL, json=BODY, headers=_headers())
    reply = seeded_client.post(
        URL, json={"summary": "Another request"}, headers=_headers()
    )
    assert reply.json()["purchase_number"] == "CB-3106"
    assert reply.json()["task_id"] == "CB-3106-T01"


def test_a_repeat_gets_the_identical_reply(
    seeded_client: TestClient, session: Session
) -> None:
    headers = _headers()
    first = seeded_client.post(URL, json=BODY, headers=headers)
    second = seeded_client.post(URL, json=BODY, headers=headers)
    assert second.status_code == 202
    assert second.json() == first.json()
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Task)) == 1


def test_the_same_key_with_another_body_is_refused(
    seeded_client: TestClient,
) -> None:
    headers = _headers()
    seeded_client.post(URL, json=BODY, headers=headers)
    reply = seeded_client.post(URL, json={"summary": "Something else"}, headers=headers)
    assert reply.status_code == 409
    error = reply.json()["error"]
    assert error["code"] == "idempotency_key_reused"
    assert REQUEST_ID.fullmatch(error["request_id"])


def test_a_missing_key_is_refused(seeded_client: TestClient) -> None:
    reply = seeded_client.post(URL, json=BODY)
    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "idempotency_key_missing"


def test_a_key_that_is_not_a_uuid_is_refused(seeded_client: TestClient) -> None:
    reply = seeded_client.post(URL, json=BODY, headers=_headers("not-a-uuid"))
    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "idempotency_key_invalid"


def test_other_fields_are_refused_and_nothing_is_saved(
    seeded_client: TestClient, session: Session
) -> None:
    sent = {"summary": "A request", "price": 10}
    reply = seeded_client.post(URL, json=sent, headers=_headers())
    assert reply.status_code == 422
    assert reply.json()["error"]["code"] == "request_invalid"
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Task)) == 0


def test_without_kab_the_service_is_not_ready(client: TestClient) -> None:
    reply = client.post(URL, json=BODY, headers=_headers())
    assert reply.status_code == 503
    assert reply.json()["error"]["code"] == "fixed_tenant_unavailable"
