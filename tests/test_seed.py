"""Tests for the seed command and the tables' tenant rules."""

import re
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from procure_pay import seed
from procure_pay.fixed_identity import FIXED_REQUESTER_ID
from procure_pay.models import Purchase, PurchaseCounter, Task, Tenant

TRACE_ID = "0" * 32


def _task(tenant_id: str, task_id: str, purchase_number: str | None) -> Task:
    return Task(
        tenant_id=tenant_id,
        task_id=task_id,
        purchase_number=purchase_number,
        requester=FIXED_REQUESTER_ID,
        status="waiting",
        trace_id=TRACE_ID,
    )


def test_seed_adds_both_tenants_and_their_counters(session: Session) -> None:
    ids = seed.seed(session)
    assert set(ids) == {"KAB Company", "Test Co."}
    assert all(re.fullmatch(r"t-[a-z0-9]{10}", tenant_id) for tenant_id in ids.values())
    counters = {
        counter.tenant_id: counter.next_number
        for counter in session.scalars(select(PurchaseCounter))
    }
    assert counters == {ids["KAB Company"]: 3105, ids["Test Co."]: 2001}


def test_seed_twice_adds_nothing_and_keeps_counters(session: Session) -> None:
    first = seed.seed(session)
    counter = session.get(PurchaseCounter, first["KAB Company"])
    assert counter is not None
    counter.next_number = 3106
    session.commit()
    assert seed.seed(session) == first
    assert session.scalar(select(func.count()).select_from(Tenant)) == 2
    assert counter.next_number == 3106


def test_seed_refuses_two_tenants_with_the_same_name(session: Session) -> None:
    session.add_all(
        [
            Tenant(tenant_id="t-aaaaaaaaaa", name="KAB Company"),
            Tenant(tenant_id="t-bbbbbbbbbb", name="KAB Company"),
        ]
    )
    session.commit()
    with pytest.raises(seed.SeedError):
        seed.seed(session)


def test_main_refuses_in_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "live")
    with pytest.raises(seed.SeedError):
        seed.main()


def test_main_seeds_the_configured_database(
    migrated_database: str, capsys: pytest.CaptureFixture[str]
) -> None:
    seed.main()
    printed = capsys.readouterr().out
    assert "KAB Company: t-" in printed
    assert "Test Co.: t-" in printed


def test_task_cannot_name_a_missing_tenant(session: Session) -> None:
    seed.seed(session)
    session.add(_task("t-zzzzzzzzzz", "TK-0001", None))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_task_cannot_point_at_another_tenants_purchase(session: Session) -> None:
    ids = seed.seed(session)
    details: dict[str, Any] = {"item": "test"}
    session.add(
        Purchase(
            tenant_id=ids["Test Co."],
            purchase_number="CB-2001",
            requester=FIXED_REQUESTER_ID,
            request_details=details,
            status="requested",
        )
    )
    session.commit()
    session.add(_task(ids["KAB Company"], "CB-2001-T01", "CB-2001"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
