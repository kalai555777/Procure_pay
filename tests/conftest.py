"""Shared test fixtures: the roles, a fresh database, sessions under each role.

The tests service logs in as the superuser. These fixtures make the roles once,
create each test's database as the superuser with the shared database's gate
rules, run the migrations as clearbuy_owner, and leave the default login as
clearbuy_tasks, as the api service and the worker use (M1-17).
"""

import os
import uuid
from collections.abc import Callable, Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import TupleRow
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session, sessionmaker

from procure_pay import db, seed, setup_database, worker
from procure_pay.graph import build_graph
from procure_pay.main import app
from procure_pay.models import Purchase, Task, Tenant
from procure_pay.purchases import get_session
from procure_pay.setup_database import OWNER_ROLE, TASKS_ROLE

type ConnectAs = Callable[[str, str], psycopg.Connection[TupleRow]]
type Login = Callable[[str], None]
type Superuser = tuple[db.DatabaseSettings, str]


def _connect(
    settings: db.DatabaseSettings, user: str, password: str, dbname: str
) -> psycopg.Connection[TupleRow]:
    # An autocommit connection as one login to one database.
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=dbname,
        user=user,
        password=password,
        autocommit=True,
    )


@pytest.fixture(scope="session")
def superuser() -> Superuser:
    # The tests service's own login, kept before any fixture switches it.
    return db.load_settings(), os.environ["DATABASE_PASSWORD"]


@pytest.fixture(scope="session")
def role_passwords(superuser: Superuser) -> dict[str, str]:
    # Make the four roles once per test run (they don't exist yet in CI).
    settings, password = superuser
    passwords = setup_database.read_passwords()
    with _connect(settings, settings.user, password, settings.name) as connection:
        setup_database.ensure_roles(connection, passwords)
    return passwords


@pytest.fixture(scope="session")
def connect_as(superuser: Superuser, role_passwords: dict[str, str]) -> ConnectAs:
    # Open a connection as any role (or the superuser), never via the environment.
    settings, password = superuser
    passwords = {settings.user: password, **role_passwords}

    def open_connection(role: str, dbname: str) -> psycopg.Connection[TupleRow]:
        return _connect(settings, role, passwords[role], dbname)

    return open_connection


@pytest.fixture
def login(monkeypatch: pytest.MonkeyPatch, role_passwords: dict[str, str]) -> Login:
    # Switch the default login that db.py reads (undone after each test).
    def switch(role: str) -> None:
        monkeypatch.setenv("DATABASE_USER", role)
        monkeypatch.setenv("DATABASE_PASSWORD", role_passwords[role])

    return switch


@pytest.fixture
def alembic_cfg() -> Config:
    config = Config()
    config.set_main_option("script_location", "migrations")
    return config


@pytest.fixture
def empty_database(
    monkeypatch: pytest.MonkeyPatch,
    superuser: Superuser,
    connect_as: ConnectAs,
    login: Login,
) -> Iterator[str]:
    settings, _ = superuser
    name = f"test_{uuid.uuid4().hex[:8]}"
    database = sql.Identifier(name)
    with connect_as(settings.user, settings.name) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(database))
        setup_database.set_database_rights(
            connection, name, setup_database.SHARED_DATABASE_ROLES
        )
    monkeypatch.setenv("DATABASE_NAME", name)
    login(TASKS_ROLE)
    try:
        yield name
    finally:
        with connect_as(settings.user, settings.name) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(database)
            )


@pytest.fixture
def empty_database_as_owner(empty_database: str, login: Login) -> str:
    login(OWNER_ROLE)
    return empty_database


@pytest.fixture
def migrated_database(empty_database: str, alembic_cfg: Config, login: Login) -> str:
    login(OWNER_ROLE)
    command.upgrade(alembic_cfg, "head")
    login(TASKS_ROLE)
    return empty_database


@pytest.fixture
def migrated_database_as_owner(migrated_database: str, login: Login) -> str:
    login(OWNER_ROLE)
    return migrated_database


@pytest.fixture
def session(migrated_database: str) -> Iterator[Session]:
    engine = db.create_app_engine(db.load_settings())
    try:
        with db.create_session_factory(engine)() as test_session:
            yield test_session
    finally:
        engine.dispose()


@pytest.fixture
def owner_session(
    migrated_database: str, superuser: Superuser, role_passwords: dict[str, str]
) -> Iterator[Session]:
    # Set-up data (tenants, the seed) is clearbuy_owner's work. The password
    # goes in the URL: db.py's hook would send the default login's password.
    settings, _ = superuser
    engine = create_engine(
        URL.create(
            drivername="postgresql+psycopg",
            username=OWNER_ROLE,
            password=role_passwords[OWNER_ROLE],
            host=settings.host,
            port=settings.port,
            database=migrated_database,
        )
    )
    try:
        with db.create_session_factory(engine)() as owner:
            yield owner
    finally:
        engine.dispose()


REQUESTER = "6f1c2e9a-3b7d-4e2a-9c5f-0d8b7a1e4c23"


@pytest.fixture
def queued_task(session: Session, owner_session: Session) -> Task:
    owner_session.add(Tenant(tenant_id="t-kabtest001", name="KAB Company"))
    owner_session.commit()
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
def seeded_client(client: TestClient, owner_session: Session) -> TestClient:
    seed.seed(owner_session)
    return client


@pytest.fixture
def session_factory(migrated_database: str) -> Iterator[sessionmaker[Session]]:
    engine = db.create_app_engine(db.load_settings())
    try:
        yield db.create_session_factory(engine)
    finally:
        engine.dispose()


@pytest.fixture
def graph(migrated_database: str) -> Iterator[worker.StubGraph]:
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        yield build_graph(PostgresSaver(pool))
    finally:
        pool.close()
