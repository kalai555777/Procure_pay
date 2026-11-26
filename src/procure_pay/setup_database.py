"""Set up the server: Clearbuy's roles, their logins, Example Co.'s database.

Run with ``python -m procure_pay.setup_database`` as the superuser: the
``setup`` Compose service on the laptop and in CI, RDS's master login in
Phase B. Safe to rerun: it creates what is missing and resets the rest.
Rights on schemas and tables come from migration job 5, not from here.
"""

import os

import psycopg
from psycopg import sql
from psycopg.rows import TupleRow

from procure_pay import db

OWNER_ROLE = "clearbuy_owner"
TASKS_ROLE = "clearbuy_tasks"
SETTINGS_ROLE = "clearbuy_settings"
EXAMPLE_ROLE = "clearbuy_example"
EXAMPLE_DATABASE = "clearbuy_example"

ROLE_PASSWORD_VARIABLES = {
    OWNER_ROLE: "CLEARBUY_OWNER_PASSWORD",
    TASKS_ROLE: "CLEARBUY_TASKS_PASSWORD",
    SETTINGS_ROLE: "CLEARBUY_SETTINGS_PASSWORD",
    EXAMPLE_ROLE: "CLEARBUY_EXAMPLE_PASSWORD",
}
SHARED_DATABASE_ROLES = (OWNER_ROLE, TASKS_ROLE, SETTINGS_ROLE)
EXAMPLE_DATABASE_ROLES = (OWNER_ROLE, EXAMPLE_ROLE)


class SetupError(Exception):
    """The set-up command cannot run safely."""


def read_passwords() -> dict[str, str]:
    """Return each role's password from its environment variable.

    Raises:
        SetupError: A variable is missing or empty. The message names the
            variable, never a value.
    """
    passwords: dict[str, str] = {}
    for role, variable in ROLE_PASSWORD_VARIABLES.items():
        password = os.environ.get(variable, "")
        if not password:
            raise SetupError(f"Set {variable} for {role}")
        passwords[role] = password
    return passwords


def connect_as_superuser(settings: db.DatabaseSettings) -> psycopg.Connection[TupleRow]:
    """Open an autocommit connection with the configured superuser login.

    Autocommit, because CREATE DATABASE cannot run inside a transaction.
    """
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name,
        user=settings.user,
        password=db.get_password(),
        autocommit=True,
    )


def ensure_roles(
    connection: psycopg.Connection[TupleRow], passwords: dict[str, str]
) -> None:
    """Create each role, or reset an existing one, with LOGIN and its password."""
    for role, password in passwords.items():
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
        ).fetchone()
        statement = (
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}")
            if exists
            else sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}")
        )
        connection.execute(
            statement.format(sql.Identifier(role), sql.Literal(password))
        )
    check_roles(connection, tuple(passwords))


def check_roles(
    connection: psycopg.Connection[TupleRow], roles: tuple[str, ...]
) -> None:
    """Refuse if a role has a special power or is a member of another role.

    Raises:
        SetupError: Names the roles and what is wrong with them.
    """
    powered = connection.execute(
        "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s) AND (rolsuper"
        " OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)"
        " ORDER BY rolname",
        (list(roles),),
    ).fetchall()
    if powered:
        names = ", ".join(row[0] for row in powered)
        raise SetupError(f"Roles with a special power: {names}")
    members = connection.execute(
        "SELECT DISTINCT r.rolname FROM pg_auth_members m"
        " JOIN pg_roles r ON r.oid = m.member"
        " WHERE r.rolname = ANY(%s) ORDER BY r.rolname",
        (list(roles),),
    ).fetchall()
    if members:
        names = ", ".join(row[0] for row in members)
        raise SetupError(f"Roles that are members of another role: {names}")


def ensure_database(connection: psycopg.Connection[TupleRow], name: str) -> None:
    """Create the database if it does not exist yet."""
    exists = connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (name,)
    ).fetchone()
    if not exists:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def set_database_rights(
    connection: psycopg.Connection[TupleRow], name: str, connect_roles: tuple[str, ...]
) -> None:
    """Let only the listed roles connect; let the owner role create schemas.

    Every role (PUBLIC) may connect to a new database by default, so that
    right is revoked first, and so is any Clearbuy role not listed.
    """
    database = sql.Identifier(name)
    connection.execute(
        sql.SQL("REVOKE CONNECT, TEMPORARY ON DATABASE {} FROM PUBLIC").format(database)
    )
    for role in ROLE_PASSWORD_VARIABLES:
        statement = (
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
            if role in connect_roles
            else sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}")
        )
        connection.execute(statement.format(database, sql.Identifier(role)))
    connection.execute(
        sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
            database, sql.Identifier(OWNER_ROLE)
        )
    )


def main() -> None:
    """Set up the roles and both databases with the configured superuser login."""
    passwords = read_passwords()
    settings = db.load_settings()
    with connect_as_superuser(settings) as connection:
        ensure_roles(connection, passwords)
        ensure_database(connection, EXAMPLE_DATABASE)
        set_database_rights(connection, settings.name, SHARED_DATABASE_ROLES)
        set_database_rights(connection, EXAMPLE_DATABASE, EXAMPLE_DATABASE_ROLES)
    for role in passwords:
        print(f"Role ready: {role}")
    print(f"Databases ready: {settings.name}, {EXAMPLE_DATABASE}")


if __name__ == "__main__":
    main()
