"""POST /v1/purchases: submit a purchase request (L1, the front door)."""

import functools
import hashlib
import json
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from procure_pay import db, tracing
from procure_pay.errors import INTERNAL_ERROR_MESSAGE, ClearbuyError
from procure_pay.fixed_identity import FIXED_REQUESTER_ID, FIXED_TENANT_NAME
from procure_pay.models import Purchase, PurchaseCounter, Task, Tenant

router = APIRouter(prefix="/v1")

FIRST_STAGE = "ST1"
NEW_PURCHASE_STATUS = "in_progress"
NEW_TASK_STATUS = "queued"


class SubmitPurchase(BaseModel):
    """What the requester sends: a summary of what they want, and nothing else."""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)


class SubmitReply(BaseModel):
    """What a submit returns at once: the purchase number, task ID and request ID."""

    purchase_number: str
    task_id: str
    request_id: str


@functools.cache
def _session_factory() -> sessionmaker[Session]:
    return db.create_session_factory(db.create_app_engine(db.load_settings()))


def get_session() -> Iterator[Session]:
    """Lend one session for one request, from the app's pool."""
    with _session_factory()() as session:
        yield session


def _parse_key(raw: str | None) -> uuid.UUID:
    if raw is None:
        raise ClearbuyError(
            "idempotency_key_missing",
            "Send an Idempotency-Key header holding a UUID.",
            400,
        )
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise ClearbuyError(
            "idempotency_key_invalid", "The Idempotency-Key header must be a UUID.", 400
        ) from None


def _fingerprint(body: SubmitPurchase) -> str:
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _not_ready() -> ClearbuyError:
    return ClearbuyError(
        "fixed_tenant_unavailable", "Clearbuy is not ready to take requests yet.", 503
    )


def _fixed_tenant_id(session: Session) -> str:
    query = select(Tenant).where(Tenant.name == FIXED_TENANT_NAME)
    tenants = session.scalars(query).all()
    if len(tenants) != 1:
        raise _not_ready()
    return tenants[0].tenant_id


def _reply_for(task: Task) -> SubmitReply:
    if task.purchase_number is None:
        raise ClearbuyError("internal_error", INTERNAL_ERROR_MESSAGE, 500)
    return SubmitReply(
        purchase_number=task.purchase_number,
        task_id=task.task_id,
        request_id=tracing.request_id_for(int(task.trace_id, 16)),
    )


@router.post("/purchases", status_code=202)
def submit_purchase(
    body: SubmitPurchase,
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> SubmitReply:
    """Save a new purchase and its first task, or return the original for a repeat."""
    key = _parse_key(idempotency_key)
    tenant_id = _fixed_tenant_id(session)
    fingerprint = _fingerprint(body)

    counter_query = (
        select(PurchaseCounter)
        .where(PurchaseCounter.tenant_id == tenant_id)
        .with_for_update()
    )
    counter = session.scalars(counter_query).one_or_none()
    if counter is None:
        raise _not_ready()

    earlier_query = select(Task).where(
        Task.tenant_id == tenant_id,
        Task.requester == FIXED_REQUESTER_ID,
        Task.idempotency_key == key,
    )
    earlier = session.scalars(earlier_query).one_or_none()
    if earlier is not None:
        if earlier.request_fingerprint != fingerprint:
            raise ClearbuyError(
                "idempotency_key_reused",
                "This Idempotency-Key was already used for a different request.",
                409,
            )
        return _reply_for(earlier)

    purchase_number = f"CB-{counter.next_number}"
    counter.next_number += 1
    trace_id = tracing.format_trace_id(tracing.current_trace_id())
    session.add(
        Purchase(
            tenant_id=tenant_id,
            purchase_number=purchase_number,
            requester=FIXED_REQUESTER_ID,
            request_details=body.model_dump(),
            stage=FIRST_STAGE,
            status=NEW_PURCHASE_STATUS,
        )
    )
    task = Task(
        tenant_id=tenant_id,
        task_id=f"{purchase_number}-T01",
        purchase_number=purchase_number,
        requester=FIXED_REQUESTER_ID,
        status=NEW_TASK_STATUS,
        idempotency_key=key,
        request_fingerprint=fingerprint,
        trace_id=trace_id,
    )
    session.add(task)
    session.commit()
    return _reply_for(task)
