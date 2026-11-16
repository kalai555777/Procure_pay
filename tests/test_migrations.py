"""Tests that the migrations build Clearbuy's tables from an empty database."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from procure_pay import db

EXPECTED_TABLES = {
    "settings.tenants",
    "tasks.purchase_counters",
    "tasks.purchases",
    "tasks.tasks",
}


@pytest.fixture
def empty_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    name = f"migration_test_{uuid.uuid4().hex[:8]}"
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


def _alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "migrations")
    return config


def _clearbuy_tables() -> set[str]:
    engine = db.create_app_engine(db.load_settings())
    try:
        inspector = inspect(engine)
        schemas = set(inspector.get_schema_names())
        return {
            f"{schema}.{table}"
            for schema in ("settings", "tasks")
            if schema in schemas
            for table in inspector.get_table_names(schema=schema)
        }
    finally:
        engine.dispose()


def test_migrations_run_from_an_empty_database(empty_database: str) -> None:
    config = _alembic_config()
    command.upgrade(config, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
    command.downgrade(config, "base")
    assert _clearbuy_tables() == set()
    command.upgrade(config, "head")
    assert _clearbuy_tables() == EXPECTED_TABLES
