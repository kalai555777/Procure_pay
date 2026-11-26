"""Failure tests (M1-17): each role reaches only its own schema and database."""

import uuid
from collections.abc import Callable, Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.errors import InsufficientPrivilege
from psycopg.rows import TupleRow
from sqlalchemy import text
from sqlalchemy.orm import Session

from procure_pay import db, setup_database
from procure_pay.setup_database import (
    EXAMPLE_ROLE,
    OWNER_ROLE,
    SETTINGS_ROLE,
    TASKS_ROLE,
)

type ConnectAs = Callable[[str, str], psycopg.Connection[TupleRow]]
type Superuser = tuple[db.DatabaseSettings, str]

ALLOWED = True
DENIED = False
DATABASE_REFUSED = "permission denied for database"

SCHEMA_CASES = [
    pytest.param(
        TASKS_ROLE, "SELECT count(*) FROM tasks.tasks", ALLOWED, id="tasks-reads-tasks"
    ),
    pytest.param(
        TASKS_ROLE,
        "SELECT count(*) FROM settings.tenants",
        ALLOWED,
        id="tasks-reads-tenants-exception",
    ),
    pytest.param(
        TASKS_ROLE,
        "INSERT INTO settings.tenants (tenant_id, name) VALUES ('t-xxxxxxxxxx', 'X')",
        DENIED,
        id="tasks-writes-tenants",
    ),
    pytest.param(
        TASKS_ROLE,
        "SELECT count(*) FROM migrations.alembic_version",
        DENIED,
        id="tasks-reads-migrations",
    ),
    pytest.param(
        TASKS_ROLE,
        "CREATE TABLE tasks.extra (id integer)",
        DENIED,
        id="tasks-creates-a-table",
    ),
    pytest.param(
        SETTINGS_ROLE,
        "SELECT count(*) FROM settings.tenants",
        ALLOWED,
        id="settings-reads-tenants",
    ),
    pytest.param(
        SETTINGS_ROLE,
        "SELECT count(*) FROM tasks.tasks",
        DENIED,
        id="settings-reads-tasks",
    ),
    pytest.param(
        SETTINGS_ROLE,
        "SELECT count(*) FROM tasks.checkpoints",
        DENIED,
        id="settings-reads-checkpoints",
    ),
    pytest.param(
        SETTINGS_ROLE,
        "SELECT count(*) FROM migrations.alembic_version",
        DENIED,
        id="settings-reads-migrations",
    ),
    pytest.param(
        SETTINGS_ROLE,
        "CREATE TABLE settings.extra (id integer)",
        DENIED,
        id="settings-creates-a-table",
    ),
]

OWN_SCHEMA = {TASKS_ROLE: "tasks", SETTINGS_ROLE: "settings"}
# The only rights outside a role's own schema: M1-22 removes the tasks entries.
TABLES_OUTSIDE = {TASKS_ROLE: [("settings", "tenants", "SELECT")], SETTINGS_ROLE: []}
DOORS_OUTSIDE = {TASKS_ROLE: [("settings",)], SETTINGS_ROLE: []}

TABLE_RIGHTS_OUTSIDE = (
    "SELECT n.nspname, c.relname, a.privilege_type FROM pg_class c"
    " JOIN pg_namespace n ON n.oid = c.relnamespace"
    " CROSS JOIN LATERAL aclexplode(c.relacl) a"
    " WHERE a.grantee = %s::regrole AND n.nspname <> %s ORDER BY 1, 2, 3"
)
SCHEMA_DOORS_OUTSIDE = (
    "SELECT n.nspname FROM pg_namespace n"
    " CROSS JOIN LATERAL aclexplode(n.nspacl) a"
    " WHERE a.grantee = %s::regrole AND n.nspname <> %s ORDER BY 1"
)


@pytest.fixture
def example_database(superuser: Superuser, connect_as: ConnectAs) -> Iterator[str]:
    settings, _ = superuser
    name = f"example_{uuid.uuid4().hex[:8]}"
    database = sql.Identifier(name)
    with connect_as(settings.user, settings.name) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(database))
        setup_database.set_database_rights(
            connection, name, setup_database.EXAMPLE_DATABASE_ROLES
        )
    try:
        yield name
    finally:
        with connect_as(settings.user, settings.name) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(database)
            )


@pytest.mark.parametrize(("role", "statement", "allowed"), SCHEMA_CASES)
def test_each_role_reaches_only_its_own_schema(
    migrated_database: str,
    connect_as: ConnectAs,
    role: str,
    statement: str,
    allowed: bool,
) -> None:
    with connect_as(role, migrated_database) as connection:
        if allowed:
            connection.execute(statement)
        else:
            with pytest.raises(InsufficientPrivilege):
                connection.execute(statement)


@pytest.mark.parametrize("role", [TASKS_ROLE, SETTINGS_ROLE])
def test_the_only_rights_outside_a_roles_schema_are_the_named_exception(
    migrated_database: str, superuser: Superuser, connect_as: ConnectAs, role: str
) -> None:
    settings, _ = superuser
    with connect_as(settings.user, migrated_database) as connection:
        tables = connection.execute(
            TABLE_RIGHTS_OUTSIDE, (role, OWN_SCHEMA[role])
        ).fetchall()
        doors = connection.execute(
            SCHEMA_DOORS_OUTSIDE, (role, OWN_SCHEMA[role])
        ).fetchall()
    assert tables == TABLES_OUTSIDE[role]
    assert doors == DOORS_OUTSIDE[role]


def test_the_app_logs_in_as_clearbuy_tasks(session: Session) -> None:
    assert session.execute(text("SELECT current_user")).scalar_one() == TASKS_ROLE


def test_the_checkpoint_pool_logs_in_as_clearbuy_tasks(migrated_database: str) -> None:
    pool = db.create_checkpoint_pool(db.load_settings())
    pool.open(wait=True, timeout=10)
    try:
        with pool.connection() as connection:
            row = connection.execute("SELECT current_user AS who").fetchone()
        assert row == {"who": TASKS_ROLE}
    finally:
        pool.close()


def test_example_login_cannot_connect_to_the_shared_database(
    empty_database: str, connect_as: ConnectAs
) -> None:
    with pytest.raises(psycopg.OperationalError, match=DATABASE_REFUSED):
        connect_as(EXAMPLE_ROLE, empty_database)


@pytest.mark.parametrize("role", [TASKS_ROLE, SETTINGS_ROLE])
def test_shared_app_logins_cannot_connect_to_example_cos_database(
    example_database: str, connect_as: ConnectAs, role: str
) -> None:
    with pytest.raises(psycopg.OperationalError, match=DATABASE_REFUSED):
        connect_as(role, example_database)


@pytest.mark.parametrize("role", [OWNER_ROLE, EXAMPLE_ROLE])
def test_owner_and_example_login_can_connect_to_example_cos_database(
    example_database: str, connect_as: ConnectAs, role: str
) -> None:
    with connect_as(role, example_database) as connection:
        assert connection.execute("SELECT current_user").fetchone() == (role,)


def test_read_passwords_names_the_missing_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLEARBUY_SETTINGS_PASSWORD")
    with pytest.raises(setup_database.SetupError, match="CLEARBUY_SETTINGS_PASSWORD"):
        setup_database.read_passwords()


def test_the_four_roles_have_no_special_powers(
    superuser: Superuser, connect_as: ConnectAs
) -> None:
    settings, _ = superuser
    with connect_as(settings.user, settings.name) as connection:
        setup_database.check_roles(
            connection, tuple(setup_database.ROLE_PASSWORD_VARIABLES)
        )


def test_check_roles_refuses_a_special_power(
    superuser: Superuser, connect_as: ConnectAs
) -> None:
    settings, _ = superuser
    with connect_as(settings.user, settings.name) as connection:
        with pytest.raises(setup_database.SetupError, match="special power"):
            setup_database.check_roles(connection, (settings.user,))


def test_check_roles_refuses_a_membership(
    superuser: Superuser, connect_as: ConnectAs
) -> None:
    settings, _ = superuser
    with connect_as(settings.user, settings.name) as connection:
        with pytest.raises(setup_database.SetupError, match="members of another"):
            setup_database.check_roles(connection, ("pg_monitor",))


def test_setup_main_is_safe_to_rerun(capsys: pytest.CaptureFixture[str]) -> None:
    setup_database.main()
    setup_database.main()
    printed = capsys.readouterr().out
    assert printed.count("Role ready: ") == 8
    assert printed.count("Databases ready: ") == 2
