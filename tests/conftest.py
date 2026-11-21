"""Shared test fixtures: a fresh database, migrated, with a session."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from procure_pay import db
from procure_pay.models import Purchase, Task, Tenant


@pytest.fixture
def alembic_cfg() -> Config:
    config = Config()
    config.set_main_option("script_location", "migrations")
    return config


@pytest.fixture
def empty_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    name = f"test_{uuid.uuid4().hex[:8]}"
    admin = db.create_app_engine(db.load_settings()).execution_options(
        isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    monkeypatch.setenv("DATABASE_NAME", name)
    try:
        yield name
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def migrated_database(empty_database: str, alembic_cfg: Config) -> str:
    command.upgrade(alembic_cfg, "head")
    return empty_database


@pytest.fixture
def session(migrated_database: str) -> Iterator[Session]:
    engine = db.create_app_engine(db.load_settings())
    try:
        with db.create_session_factory(engine)() as test_session:
            yield test_session
    finally:
        engine.dispose()


REQUESTER = "6f1c2e9a-3b7d-4e2a-9c5f-0d8b7a1e4c23"


@pytest.fixture
def queued_task(session: Session) -> Task:
    session.add(Tenant(tenant_id="t-kabtest001", name="KAB Company"))
    session.flush()
    session.add(
        Purchase(
            tenant_id="t-kabtest001",
            purchase_number="CB-3105",
            requester=REQUESTER,
            request_details={"summary": "Renew Solid licences"},
            stage="ST1",
            status="in_progress",
        )
    )
    session.flush()
    task = Task(
        tenant_id="t-kabtest001",
        task_id="CB-3105-T01",
        purchase_number="CB-3105",
        requester=REQUESTER,
        status="queued",
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
    )
    session.add(task)
    session.commit()
    return task
