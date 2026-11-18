"""Shared test fixtures: a fresh database, migrated, with a session."""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from procure_pay import db


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
